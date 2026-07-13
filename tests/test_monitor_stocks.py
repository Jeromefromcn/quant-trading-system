"""monitor_stocks.py 的每日報告測試 : 讀檔/日期過濾用 tmp_path, 格式化與發送用手造資料或 mock"""
import json
from datetime import date, datetime, time, timedelta

import pytest

import monitor_stocks


def test_load_records_for_date_filters_by_market_date_eastern(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    record_before = {"market_date_eastern": "2026-07-09", "marker": "yesterday"}
    record_after = {"market_date_eastern": "2026-07-10", "marker": "today"}
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record_before) + "\n")
        log_file.write(json.dumps(record_after) + "\n")

    records = monitor_stocks._load_records_for_date(log_file_path, date(2026, 7, 10))

    assert len(records) == 1
    assert records[0]["marker"] == "today"


def test_load_records_for_date_returns_empty_list_when_file_missing(tmp_path):
    missing_log_file_path = str(tmp_path / "does_not_exist.jsonl")

    records = monitor_stocks._load_records_for_date(missing_log_file_path, date(2026, 7, 10))

    assert records == []


def test_load_records_for_date_skips_valid_json_that_is_not_a_dict(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    valid_record = {"market_date_eastern": "2026-07-10", "marker": "today"}
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(json.dumps(None) + "\n")
        log_file.write(json.dumps(valid_record) + "\n")

    records = monitor_stocks._load_records_for_date(log_file_path, date(2026, 7, 10))

    assert len(records) == 1
    assert records[0]["marker"] == "today"


def test_format_daily_report_reports_no_records_when_empty():
    report = monitor_stocks._format_daily_report([], date(2026, 7, 10))

    assert "美股每日報告 (2026-07-10 美東交易日)" in report
    assert "當日無任何執行紀錄" in report


def test_format_daily_report_reports_market_closed():
    records = [{"market_date_eastern": "2026-07-11", "market_open": False, "symbols": {}}]

    report = monitor_stocks._format_daily_report(records, date(2026, 7, 11))

    assert "今日美股休市, 無交易" in report


def test_format_daily_report_lists_submitted_orders():
    records = [
        {
            "market_date_eastern": "2026-07-10",
            "market_open": True,
            "account_equity_usd": 10_000.0,
            "day_start_equity_usd": 10_000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {
                "VOO": {
                    "risk_decision": {"type": "OrderEvent"},
                    "execution_result": {
                        "type": "SubmittedEvent", "symbol": "VOO", "side": "BUY",
                        "quantity": 10.0, "order_id": "order-1", "limit_price": 550.25,
                    },
                    "current_share_balance": 0.0,
                    "signal": {"latest_close_price": 550.25},
                },
                "QQQ": {
                    "risk_decision": {"type": "NoActionNeeded"},
                    "execution_result": None,
                    "current_share_balance": 0.0,
                    "signal": {"latest_close_price": 480.0},
                },
            },
        },
    ]

    report = monitor_stocks._format_daily_report(records, date(2026, 7, 10))

    assert "VOO: 買入 10.0 股 @ 550.25 限價 開盤委託已送出 (order_id=order-1)" in report
    assert "今日無新委託送出" not in report


def test_format_daily_report_shows_equity_change_percentage():
    records = [
        {
            "market_date_eastern": "2026-07-10",
            "market_open": True,
            "account_equity_usd": 9_900.0,
            "day_start_equity_usd": 10_000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {},
        },
    ]

    report = monitor_stocks._format_daily_report(records, date(2026, 7, 10))

    assert "帳戶淨值從 10000.00 變化至 9900.00 USD (-1.00%)" in report


def test_main_loads_formats_and_sends_report_for_previous_eastern_trading_day(monkeypatch):
    captured = {}

    def _fake_load_records_for_date(log_file_path, target_date):
        captured["log_file_path"] = log_file_path
        captured["target_date"] = target_date
        return [{"marker": "fake_record", "market_open": True}]

    def _fake_format_daily_report(records, target_date):
        captured["records"] = records
        captured["format_target_date"] = target_date
        return "格式化後的報告文字"

    sent_messages = []
    monkeypatch.setattr(monitor_stocks, "_load_records_for_date", _fake_load_records_for_date)
    monkeypatch.setattr(monitor_stocks, "_format_daily_report", _fake_format_daily_report)
    monkeypatch.setattr(
        monitor_stocks.telegram_alerts, "send_alert", lambda message: sent_messages.append(message)
    )

    now_eastern = datetime(2026, 7, 11, 7, 50, 0)
    monitor_stocks.main(now_eastern=now_eastern)

    expected_target_date = (now_eastern - timedelta(days=1)).date()
    assert captured["target_date"] == expected_target_date
    assert captured["format_target_date"] == expected_target_date
    assert captured["records"] == [{"marker": "fake_record", "market_open": True}]
    assert sent_messages == ["格式化後的報告文字"]


def test_main_skips_when_outside_target_window(monkeypatch):
    was_called = {"called": False}
    monkeypatch.setattr(
        monitor_stocks, "_load_records_for_date",
        lambda log_file_path, target_date: was_called.update(called=True),
    )
    sent_messages = []
    monkeypatch.setattr(
        monitor_stocks.telegram_alerts, "send_alert", lambda message: sent_messages.append(message)
    )

    now_eastern = datetime(2026, 7, 11, 12, 0, 0)
    monitor_stocks.main(now_eastern=now_eastern)

    assert was_called["called"] is False
    assert sent_messages == []


def test_main_skips_when_previous_day_was_not_a_trading_day(monkeypatch):
    monkeypatch.setattr(
        monitor_stocks, "_load_records_for_date",
        lambda log_file_path, target_date: [{"market_date_eastern": str(target_date), "market_open": False}],
    )
    sent_messages = []
    monkeypatch.setattr(
        monitor_stocks.telegram_alerts, "send_alert", lambda message: sent_messages.append(message)
    )

    now_eastern = datetime(2026, 7, 13, 7, 50, 0)
    monitor_stocks.main(now_eastern=now_eastern)

    assert sent_messages == []


def test_is_within_target_window_before_start_returns_false():
    now_eastern = datetime(2026, 7, 13, 7, 44, 59)

    assert monitor_stocks._is_within_target_window(now_eastern) is False


def test_is_within_target_window_at_start_returns_true():
    now_eastern = datetime(2026, 7, 13, 7, 45, 0)

    assert monitor_stocks._is_within_target_window(now_eastern) is True


def test_is_within_target_window_inside_returns_true():
    now_eastern = datetime(2026, 7, 13, 7, 50, 0)

    assert monitor_stocks._is_within_target_window(now_eastern) is True


def test_is_within_target_window_at_end_returns_false():
    now_eastern = datetime(2026, 7, 13, 8, 0, 0)

    assert monitor_stocks._is_within_target_window(now_eastern) is False


def test_is_within_target_window_after_end_returns_false():
    now_eastern = datetime(2026, 7, 13, 9, 0, 0)

    assert monitor_stocks._is_within_target_window(now_eastern) is False
