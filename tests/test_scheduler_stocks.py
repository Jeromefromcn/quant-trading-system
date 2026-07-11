"""scheduler_stocks.py 的排程安全網測試 : 鎖行為與告警分流全程 mock, 不碰真正鎖檔或外部網路"""
import fcntl

import pytest

import scheduler_stocks


def test_format_run_summary_reports_submitted_order():
    record = {
        "run_started_at": "2026-07-10T20:35:00+00:00",
        "symbols": {
            "VOO": {
                "risk_decision": {"type": "OrderEvent", "symbol": "VOO", "side": "BUY", "quantity": 10.0},
                "execution_result": {
                    "type": "SubmittedEvent", "symbol": "VOO", "side": "BUY", "quantity": 10.0,
                    "order_id": "order-1", "limit_price": 550.25,
                },
            },
            "QQQ": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None},
        },
    }

    summary = scheduler_stocks._format_run_summary(record)

    assert "VOO: 買入 10.0 股委託已送出 (order_id=order-1), 待次日開盤確認成交" in summary
    assert "QQQ: 本次無動作" in summary


def test_format_run_summary_reports_rejection_reason_and_values():
    record = {
        "run_started_at": "2026-07-10T20:35:00+00:00",
        "symbols": {
            "QQQ": {
                "risk_decision": {
                    "type": "RejectionEvent", "symbol": "QQQ", "reason": "correlation_exceeds_limit",
                    "computed_value": 0.87, "limit_value": 0.8,
                },
                "execution_result": None,
            },
        },
    }

    summary = scheduler_stocks._format_run_summary(record)

    assert "QQQ: 交易被風控擋下 (correlation_exceeds_limit, 實際值=0.87, 上限=0.8)" in summary


def test_run_scheduled_calls_run_once_when_lock_available(tmp_path, monkeypatch):
    lock_file_path = str(tmp_path / "scheduler_stocks.lock")
    call_count = {"n": 0}

    def _fake_run_once():
        call_count["n"] += 1
        return {"symbols": {}, "market_open": False}

    monkeypatch.setattr(scheduler_stocks.run_once_stocks, "run_once", _fake_run_once)

    result = scheduler_stocks.run_scheduled(lock_file_path)

    assert call_count["n"] == 1
    assert result == {"symbols": {}, "market_open": False}


def test_run_scheduled_raises_when_lock_already_held(tmp_path, monkeypatch):
    lock_file_path = str(tmp_path / "scheduler_stocks.lock")
    holder_file = open(lock_file_path, "w")
    fcntl.flock(holder_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        was_called = {"called": False}
        monkeypatch.setattr(
            scheduler_stocks.run_once_stocks, "run_once", lambda: was_called.update(called=True)
        )

        with pytest.raises(scheduler_stocks.SchedulerLockedError):
            scheduler_stocks.run_scheduled(lock_file_path)

        assert was_called["called"] is False
    finally:
        holder_file.close()


def test_main_skips_summary_when_market_closed(monkeypatch):
    fake_record = {"symbols": {}, "market_open": False}
    monkeypatch.setattr(scheduler_stocks, "run_scheduled", lambda lock_file_path: fake_record)
    alerts = []
    monkeypatch.setattr(
        scheduler_stocks.telegram_alerts, "send_alert", lambda message: alerts.append(message)
    )

    with pytest.raises(SystemExit) as exit_info:
        scheduler_stocks.main()

    assert exit_info.value.code == 0
    assert alerts == []


def test_main_sends_summary_alert_and_exits_zero_when_market_open(monkeypatch):
    fake_record = {
        "run_started_at": "2026-07-10T20:35:00+00:00",
        "market_open": True,
        "symbols": {"VOO": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None}},
    }
    monkeypatch.setattr(scheduler_stocks, "run_scheduled", lambda lock_file_path: fake_record)
    alerts = []
    monkeypatch.setattr(
        scheduler_stocks.telegram_alerts, "send_alert", lambda message: alerts.append(message)
    )

    with pytest.raises(SystemExit) as exit_info:
        scheduler_stocks.main()

    assert exit_info.value.code == 0
    assert len(alerts) == 1


def test_main_sends_alert_and_exits_zero_when_locked(monkeypatch):
    def _raise_locked(lock_file_path):
        raise scheduler_stocks.SchedulerLockedError("鎖仍被持有")

    monkeypatch.setattr(scheduler_stocks, "run_scheduled", _raise_locked)
    alerts = []
    monkeypatch.setattr(
        scheduler_stocks.telegram_alerts, "send_alert", lambda message: alerts.append(message)
    )

    with pytest.raises(SystemExit) as exit_info:
        scheduler_stocks.main()

    assert exit_info.value.code == 0
    assert len(alerts) == 1
    assert "尚未結束" in alerts[0]


def test_main_sends_alert_and_exits_one_when_run_once_raises(monkeypatch):
    def _raise_unexpected(lock_file_path):
        raise RuntimeError("模擬 API 無回應")

    monkeypatch.setattr(scheduler_stocks, "run_scheduled", _raise_unexpected)
    alerts = []
    monkeypatch.setattr(
        scheduler_stocks.telegram_alerts, "send_alert", lambda message: alerts.append(message)
    )

    with pytest.raises(SystemExit) as exit_info:
        scheduler_stocks.main()

    assert exit_info.value.code == 1
    assert len(alerts) == 1
    assert "模擬 API 無回應" in alerts[0]


def test_main_does_not_send_summary_when_notify_disabled(monkeypatch):
    fake_record = {
        "run_started_at": "2026-07-08T09:05:53+00:00",
        "market_open": True,
        "symbols": {
            "VOO": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None},
        },
    }
    monkeypatch.setattr(scheduler_stocks, "run_scheduled", lambda lock_file_path: fake_record)
    monkeypatch.setattr(scheduler_stocks, "NOTIFY_RUN_SUMMARY", False)
    alerts = []
    monkeypatch.setattr(scheduler_stocks.telegram_alerts, "send_alert", lambda message: alerts.append(message))

    with pytest.raises(SystemExit) as exit_info:
        scheduler_stocks.main()

    assert exit_info.value.code == 0
    assert alerts == []


def test_format_run_summary_reports_execution_failure_reason():
    record = {
        "run_started_at": "2026-07-10T20:35:00+00:00",
        "symbols": {
            "VOO": {
                "risk_decision": {
                    "type": "OrderEvent", "symbol": "VOO", "side": "SELL", "quantity": 10.0,
                },
                "execution_result": {
                    "type": "FailEvent", "symbol": "VOO",
                    "reason": "insufficient_buying_power",
                },
            },
        },
    }

    summary = scheduler_stocks._format_run_summary(record)

    assert "VOO: 下單失敗 (insufficient_buying_power)" in summary
