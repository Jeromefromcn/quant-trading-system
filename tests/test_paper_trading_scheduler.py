"""scheduler.py 的排程安全網測試 : 鎖行為與告警分流全程 mock, 不碰真正鎖檔或外部網路"""
import fcntl
import os

import pytest

import scheduler


def test_format_run_summary_reports_no_trade_when_all_no_action():
    record = {
        "run_started_at": "2026-07-08T09:05:53+00:00",
        "symbols": {
            "BTCUSDT": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None},
            "ETHUSDT": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None},
        },
    }

    summary = scheduler._format_run_summary(record)

    assert "本次無成交" in summary
    assert "BTCUSDT: 本次無動作" in summary
    assert "ETHUSDT: 本次無動作" in summary


def test_format_run_summary_reports_trade_when_fill_event_present():
    record = {
        "run_started_at": "2026-07-08T09:05:53+00:00",
        "symbols": {
            "BTCUSDT": {
                "risk_decision": {
                    "type": "OrderEvent", "symbol": "BTCUSDT", "side": "BUY", "quantity": 0.015,
                },
                "execution_result": {
                    "type": "FillEvent", "symbol": "BTCUSDT", "side": "BUY", "quantity": 0.015,
                    "average_price": 68125.3, "order_id": "3021984710",
                    "commission": 0.0000045, "commission_asset": "BTC",
                },
            },
            "ETHUSDT": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None},
        },
    }

    summary = scheduler._format_run_summary(record)

    assert "本次有成交" in summary
    assert "BTCUSDT: 買入 0.015 @ 68125.3 成交 (order_id=3021984710)" in summary
    assert "ETHUSDT: 本次無動作" in summary


def test_format_run_summary_reports_rejection_reason_and_values():
    record = {
        "run_started_at": "2026-07-08T09:05:53+00:00",
        "symbols": {
            "ETHUSDT": {
                "risk_decision": {
                    "type": "RejectionEvent", "symbol": "ETHUSDT",
                    "reason": "correlation_exceeds_limit",
                    "computed_value": 0.87, "limit_value": 0.8,
                },
                "execution_result": None,
            },
        },
    }

    summary = scheduler._format_run_summary(record)

    assert "本次無成交" in summary
    assert "ETHUSDT: 交易被風控擋下 (correlation_exceeds_limit, 實際值=0.87, 上限=0.8)" in summary


def test_format_run_summary_reports_execution_failure_reason():
    record = {
        "run_started_at": "2026-07-08T09:05:53+00:00",
        "symbols": {
            "BTCUSDT": {
                "risk_decision": {
                    "type": "OrderEvent", "symbol": "BTCUSDT", "side": "SELL", "quantity": 0.01,
                },
                "execution_result": {
                    "type": "FailEvent", "symbol": "BTCUSDT",
                    "reason": "insufficient_balance", "raw_exchange_response": "{}",
                },
            },
        },
    }

    summary = scheduler._format_run_summary(record)

    assert "本次無成交" in summary
    assert "BTCUSDT: 下單失敗 (insufficient_balance)" in summary


def test_run_scheduled_calls_run_once_when_lock_available(tmp_path, monkeypatch):
    lock_file_path = str(tmp_path / "scheduler.lock")
    call_count = {"n": 0}

    def _fake_run_once():
        call_count["n"] += 1
        return {"symbols": {}}

    monkeypatch.setattr(scheduler.run_once, "run_once", _fake_run_once)

    result = scheduler.run_scheduled(lock_file_path)

    assert call_count["n"] == 1
    assert result == {"symbols": {}}


def test_run_scheduled_raises_when_lock_already_held(tmp_path, monkeypatch):
    lock_file_path = str(tmp_path / "scheduler.lock")
    holder_file = open(lock_file_path, "w")
    fcntl.flock(holder_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        was_called = {"called": False}
        monkeypatch.setattr(
            scheduler.run_once, "run_once", lambda: was_called.update(called=True)
        )

        with pytest.raises(scheduler.SchedulerLockedError):
            scheduler.run_scheduled(lock_file_path)

        assert was_called["called"] is False
    finally:
        holder_file.close()


def test_main_sends_summary_alert_and_exits_zero_when_successful(monkeypatch):
    fake_record = {
        "run_started_at": "2026-07-08T09:05:53+00:00",
        "symbols": {
            "BTCUSDT": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None},
        },
    }
    monkeypatch.setattr(scheduler, "run_scheduled", lambda lock_file_path: fake_record)
    alerts = []
    monkeypatch.setattr(scheduler.telegram_alerts, "send_alert", lambda message: alerts.append(message))

    with pytest.raises(SystemExit) as exit_info:
        scheduler.main()

    assert exit_info.value.code == 0
    assert len(alerts) == 1
    assert alerts[0] == scheduler._format_run_summary(fake_record)


def test_main_does_not_send_summary_when_notify_disabled(monkeypatch):
    fake_record = {
        "run_started_at": "2026-07-08T09:05:53+00:00",
        "symbols": {
            "BTCUSDT": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None},
        },
    }
    monkeypatch.setattr(scheduler, "run_scheduled", lambda lock_file_path: fake_record)
    monkeypatch.setattr(scheduler, "NOTIFY_RUN_SUMMARY", False)
    alerts = []
    monkeypatch.setattr(scheduler.telegram_alerts, "send_alert", lambda message: alerts.append(message))

    with pytest.raises(SystemExit) as exit_info:
        scheduler.main()

    assert exit_info.value.code == 0
    assert alerts == []


def test_main_sends_alert_and_exits_zero_when_locked(monkeypatch):
    def _raise_locked(lock_file_path):
        raise scheduler.SchedulerLockedError("鎖仍被持有")

    monkeypatch.setattr(scheduler, "run_scheduled", _raise_locked)
    alerts = []
    monkeypatch.setattr(scheduler.telegram_alerts, "send_alert", lambda message: alerts.append(message))

    with pytest.raises(SystemExit) as exit_info:
        scheduler.main()

    assert exit_info.value.code == 0
    assert len(alerts) == 1
    assert "尚未結束" in alerts[0]


def test_main_sends_alert_and_exits_one_when_run_once_raises(monkeypatch):
    def _raise_unexpected(lock_file_path):
        raise RuntimeError("模擬 API 無回應")

    monkeypatch.setattr(scheduler, "run_scheduled", _raise_unexpected)
    alerts = []
    monkeypatch.setattr(scheduler.telegram_alerts, "send_alert", lambda message: alerts.append(message))

    with pytest.raises(SystemExit) as exit_info:
        scheduler.main()

    assert exit_info.value.code == 1
    assert len(alerts) == 1
    assert "模擬 API 無回應" in alerts[0]
