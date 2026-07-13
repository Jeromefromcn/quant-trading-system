"""scheduler_stocks.py 的排程安全網測試 : 鎖行為與告警分流全程 mock, 不碰真正鎖檔或外部網路"""
import fcntl
from datetime import datetime

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
    monkeypatch.setattr(scheduler_stocks, "_should_run_now", lambda now_eastern, log_file_path: True)
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
    monkeypatch.setattr(scheduler_stocks, "_should_run_now", lambda now_eastern, log_file_path: True)
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
    monkeypatch.setattr(scheduler_stocks, "_should_run_now", lambda now_eastern, log_file_path: True)
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
    monkeypatch.setattr(scheduler_stocks, "_should_run_now", lambda now_eastern, log_file_path: True)
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
    monkeypatch.setattr(scheduler_stocks, "_should_run_now", lambda now_eastern, log_file_path: True)
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


def test_is_within_target_window_before_start_returns_false():
    now_eastern = datetime(2026, 7, 13, 16, 34, 59)

    assert scheduler_stocks._is_within_target_window(now_eastern) is False


def test_is_within_target_window_at_start_returns_true():
    now_eastern = datetime(2026, 7, 13, 16, 35, 0)

    assert scheduler_stocks._is_within_target_window(now_eastern) is True


def test_is_within_target_window_inside_returns_true():
    now_eastern = datetime(2026, 7, 13, 17, 0, 0)

    assert scheduler_stocks._is_within_target_window(now_eastern) is True


def test_is_within_target_window_at_end_returns_false():
    now_eastern = datetime(2026, 7, 13, 17, 35, 0)

    assert scheduler_stocks._is_within_target_window(now_eastern) is False


def test_is_within_target_window_after_end_returns_false():
    now_eastern = datetime(2026, 7, 13, 18, 0, 0)

    assert scheduler_stocks._is_within_target_window(now_eastern) is False


def test_has_already_run_today_returns_false_when_file_missing(tmp_path):
    log_file_path = str(tmp_path / "does_not_exist.jsonl")

    assert scheduler_stocks._has_already_run_today(log_file_path, "2026-07-13") is False


def test_has_already_run_today_returns_false_when_file_empty(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    open(log_file_path, "w", encoding="utf-8").close()

    assert scheduler_stocks._has_already_run_today(log_file_path, "2026-07-13") is False


def test_has_already_run_today_returns_false_when_last_line_malformed(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write('{"market_date_eastern": "2026-07-13"}\n')
        log_file.write("not valid json\n")

    assert scheduler_stocks._has_already_run_today(log_file_path, "2026-07-13") is False


def test_has_already_run_today_returns_true_when_last_record_is_today(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write('{"market_date_eastern": "2026-07-10"}\n')
        log_file.write('{"market_date_eastern": "2026-07-13"}\n')

    assert scheduler_stocks._has_already_run_today(log_file_path, "2026-07-13") is True


def test_has_already_run_today_returns_false_when_last_record_is_earlier_date(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write('{"market_date_eastern": "2026-07-10"}\n')

    assert scheduler_stocks._has_already_run_today(log_file_path, "2026-07-13") is False


def test_should_run_now_true_when_in_window_and_not_run_yet(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    now_eastern = datetime(2026, 7, 13, 17, 0, 0)

    assert scheduler_stocks._should_run_now(now_eastern, log_file_path) is True


def test_should_run_now_false_when_outside_window(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    now_eastern = datetime(2026, 7, 13, 12, 0, 0)

    assert scheduler_stocks._should_run_now(now_eastern, log_file_path) is False


def test_should_run_now_false_when_already_run_today(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write('{"market_date_eastern": "2026-07-13"}\n')
    now_eastern = datetime(2026, 7, 13, 17, 0, 0)

    assert scheduler_stocks._should_run_now(now_eastern, log_file_path) is False


def test_main_exits_early_without_calling_run_scheduled_when_should_run_now_is_false(monkeypatch):
    monkeypatch.setattr(scheduler_stocks, "_should_run_now", lambda now_eastern, log_file_path: False)
    was_called = {"called": False}
    monkeypatch.setattr(
        scheduler_stocks, "run_scheduled", lambda lock_file_path: was_called.update(called=True)
    )

    with pytest.raises(SystemExit) as exit_info:
        scheduler_stocks.main()

    assert exit_info.value.code == 0
    assert was_called["called"] is False
