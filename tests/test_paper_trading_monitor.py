"""monitor.py 的每日報告測試 : 讀檔/日期過濾用 tmp_path, 格式化與發送用手造資料或 mock"""
import json
from datetime import date

import pytest

import monitor


def test_load_records_for_date_filters_by_utc_date_boundary(tmp_path):
    log_file_path = str(tmp_path / "run_log.jsonl")
    record_before_boundary = {"run_started_at": "2026-07-07T23:59:59+00:00", "marker": "yesterday"}
    record_after_boundary = {"run_started_at": "2026-07-08T00:00:01+00:00", "marker": "today"}
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record_before_boundary) + "\n")
        log_file.write(json.dumps(record_after_boundary) + "\n")

    records = monitor._load_records_for_date(log_file_path, date(2026, 7, 8))

    assert len(records) == 1
    assert records[0]["marker"] == "today"


def test_load_records_for_date_returns_empty_list_when_file_missing(tmp_path):
    missing_log_file_path = str(tmp_path / "does_not_exist.jsonl")

    records = monitor._load_records_for_date(missing_log_file_path, date(2026, 7, 8))

    assert records == []


def test_format_daily_report_reports_no_records_when_empty():
    report = monitor._format_daily_report([], date(2026, 7, 8))

    assert "每日報告 (2026-07-08 UTC)" in report
    assert "當日無任何執行紀錄" in report
    assert "今日無成交" not in report


def test_format_daily_report_lists_fill_events():
    records = [
        {
            "run_started_at": "2026-07-08T12:00:01+00:00",
            "account_equity_usdt": 10000.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {
                "BTCUSDT": {
                    "risk_decision": {"type": "OrderEvent"},
                    "execution_result": {
                        "type": "FillEvent", "symbol": "BTCUSDT", "side": "BUY",
                        "quantity": 0.015, "average_price": 68125.3, "order_id": "1",
                    },
                    "current_base_asset_balance": 0.015,
                    "signal": {"latest_close_price": 68125.3},
                },
                "ETHUSDT": {
                    "risk_decision": {"type": "NoActionNeeded"},
                    "execution_result": None,
                    "current_base_asset_balance": 0.0,
                    "signal": {"latest_close_price": 3500.0},
                },
            },
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "12:00 UTC BTCUSDT: 買入 0.015 @ 68125.3" in report
    assert "今日無成交" not in report


def test_format_daily_report_reports_no_fills_when_all_no_action():
    records = [
        {
            "run_started_at": "2026-07-08T12:00:01+00:00",
            "account_equity_usdt": 10000.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {
                "BTCUSDT": {
                    "risk_decision": {"type": "NoActionNeeded"},
                    "execution_result": None,
                    "current_base_asset_balance": 0.0,
                    "signal": {"latest_close_price": 68125.3},
                },
            },
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "今日無成交" in report


def test_format_daily_report_counts_runs_and_rejections():
    records = [
        {
            "run_started_at": "2026-07-08T08:00:00+00:00",
            "account_equity_usdt": 10000.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {
                "BTCUSDT": {
                    "risk_decision": {
                        "type": "RejectionEvent", "reason": "max_loss_per_trade",
                        "computed_value": 0.02, "limit_value": 0.015,
                    },
                    "execution_result": None,
                    "current_base_asset_balance": 0.0,
                    "signal": {"latest_close_price": 68000.0},
                },
            },
        },
        {
            "run_started_at": "2026-07-08T12:00:00+00:00",
            "account_equity_usdt": 10000.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {
                "ETHUSDT": {
                    "risk_decision": {
                        "type": "RejectionEvent", "reason": "correlation_limit",
                        "computed_value": 0.9, "limit_value": 0.8,
                    },
                    "execution_result": None,
                    "current_base_asset_balance": 0.0,
                    "signal": {"latest_close_price": 3500.0},
                },
            },
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "今日排程執行 2 / 預期 6 次" in report
    assert "風控拒絕 2 次" in report


def test_format_daily_report_shows_equity_change_percentage():
    records = [
        {
            "run_started_at": "2026-07-08T00:00:00+00:00",
            "account_equity_usdt": 9800.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {},
        },
        {
            "run_started_at": "2026-07-08T20:00:00+00:00",
            "account_equity_usdt": 9700.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {},
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "帳戶淨值從 10000.00 變化至 9700.00 USDT (-3.00%)" in report


def test_format_daily_report_lists_nonzero_positions():
    records = [
        {
            "run_started_at": "2026-07-08T20:00:00+00:00",
            "account_equity_usdt": 10000.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {
                "BTCUSDT": {
                    "risk_decision": {"type": "NoActionNeeded"},
                    "execution_result": None,
                    "current_base_asset_balance": 0.015,
                    "signal": {"latest_close_price": 68000.0},
                },
                "ETHUSDT": {
                    "risk_decision": {"type": "NoActionNeeded"},
                    "execution_result": None,
                    "current_base_asset_balance": 0.0,
                    "signal": {"latest_close_price": 3500.0},
                },
            },
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "BTCUSDT: 0.015 (約 1020.00 USDT)" in report
    assert "ETHUSDT:" not in report


def test_format_daily_report_shows_no_positions_when_all_zero():
    records = [
        {
            "run_started_at": "2026-07-08T20:00:00+00:00",
            "account_equity_usdt": 10000.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {
                "BTCUSDT": {
                    "risk_decision": {"type": "NoActionNeeded"},
                    "execution_result": None,
                    "current_base_asset_balance": 0.0,
                    "signal": {"latest_close_price": 68000.0},
                },
            },
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "目前無持倉" in report


def test_format_daily_report_counts_staleness_and_circuit_breaker_triggers():
    records = [
        {
            "run_started_at": "2026-07-08T08:00:00+00:00",
            "account_equity_usdt": 9600.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {"BTCUSDT": {"time_since_close_seconds": 999, "threshold_seconds": 129600}},
            "circuit_breaker_triggered": True,
            "symbols": {},
        },
        {
            "run_started_at": "2026-07-08T12:00:00+00:00",
            "account_equity_usdt": 9600.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {},
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "數據異常保護觸發 1 次" in report
    assert "每日熔斷觸發 1 次" in report
