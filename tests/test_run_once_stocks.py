"""run_once_stocks.py 的編排邏輯測試: monkeypatch 掉所有 agent 與外部狀態, 只驗證串接順序與紀錄格式正確"""
from datetime import datetime, timezone

import pandas as pd
import pytest

import run_once_stocks
from events import OrderEvent, SignalEvent, SubmittedEvent


def _make_ohlcv_dataframe():
    current_time = pd.Timestamp.now(tz="UTC").tz_localize(None)
    return pd.DataFrame(
        {
            "open_time": [current_time],
            "open": [550.0],
            "high": [551.0],
            "low": [549.0],
            "close": [550.0],
            "volume": [1_000_000.0],
        }
    )


def _make_signal_event(symbol: str, target_position: int) -> SignalEvent:
    return SignalEvent(
        symbol=symbol,
        target_position=target_position,
        as_of_timestamp=datetime(2026, 7, 10, tzinfo=timezone.utc),
        latest_close_price=550.0,
        latest_average_true_range=5.0,
    )


def _patch_common(monkeypatch, tmp_path):
    """幾乎每個測試都需要的共用 monkeypatch: 記錄檔與每日狀態檔路徑指到 tmp_path, 攔截 Telegram 警報,
    並預設今天是交易日(個別測試需要非交易日情境時再自行覆寫)"""
    monkeypatch.setattr(run_once_stocks, "LOG_FILE_PATH", str(tmp_path / "run_log_stocks.jsonl"))
    monkeypatch.setattr(
        run_once_stocks, "DAILY_STATE_FILE_PATH", str(tmp_path / "daily_risk_state_stocks.json")
    )
    monkeypatch.setattr(run_once_stocks.telegram_alerts, "send_alert", lambda message: None)
    monkeypatch.setattr(
        run_once_stocks.alpaca_paper_trading_client,
        "get_todays_calendar_entry",
        lambda today: {"date": today, "open": "09:30", "close": "16:00"},
    )


def test_run_once_records_market_closed_as_no_op_without_fetching_data(tmp_path, monkeypatch):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        run_once_stocks.alpaca_paper_trading_client, "get_todays_calendar_entry", lambda today: None
    )
    fetch_calls = []
    monkeypatch.setattr(
        run_once_stocks.stock_data_agent,
        "fetch_latest_daily_bars",
        lambda symbol: fetch_calls.append(symbol) or _make_ohlcv_dataframe(),
    )

    record = run_once_stocks.run_once(symbols=["VOO"])

    assert record["market_open"] is False
    assert fetch_calls == []
    assert record["symbols"] == {}


def test_run_once_logs_no_action_when_risk_agent_returns_none(tmp_path, monkeypatch):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        run_once_stocks.stock_data_agent,
        "fetch_latest_daily_bars",
        lambda symbol: _make_ohlcv_dataframe(),
    )
    monkeypatch.setattr(
        run_once_stocks.signal_agent,
        "decide",
        lambda ohlcv_dataframe, symbol: _make_signal_event(symbol, 0),
    )
    monkeypatch.setattr(
        run_once_stocks.alpaca_paper_trading_client,
        "get_account",
        lambda: {"equity": 10_000.0, "cash": 10_000.0},
    )
    monkeypatch.setattr(run_once_stocks.alpaca_paper_trading_client, "get_positions", lambda: {})
    monkeypatch.setattr(
        run_once_stocks.risk_agent, "review_portfolio", lambda *args, **kwargs: {"VOO": None}
    )

    record = run_once_stocks.run_once(symbols=["VOO"])

    assert record["market_open"] is True
    assert record["symbols"]["VOO"]["risk_decision"]["type"] == "NoActionNeeded"
    assert record["symbols"]["VOO"]["execution_result"] is None


def test_run_once_submits_order_when_risk_agent_approves(tmp_path, monkeypatch):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        run_once_stocks.stock_data_agent,
        "fetch_latest_daily_bars",
        lambda symbol: _make_ohlcv_dataframe(),
    )
    monkeypatch.setattr(
        run_once_stocks.signal_agent,
        "decide",
        lambda ohlcv_dataframe, symbol: _make_signal_event(symbol, 1),
    )
    monkeypatch.setattr(
        run_once_stocks.alpaca_paper_trading_client,
        "get_account",
        lambda: {"equity": 10_000.0, "cash": 10_000.0},
    )
    monkeypatch.setattr(run_once_stocks.alpaca_paper_trading_client, "get_positions", lambda: {})
    approved_order = OrderEvent(symbol="VOO", side="BUY", quantity=10.0, limit_price=550.0)
    monkeypatch.setattr(
        run_once_stocks.risk_agent, "review_portfolio", lambda *args, **kwargs: {"VOO": approved_order}
    )
    submitted_event = SubmittedEvent(
        symbol="VOO", side="BUY", quantity=10.0, order_id="order-1", limit_price=550.0
    )
    monkeypatch.setattr(
        run_once_stocks.stock_execution_agent, "execute", lambda order_event: submitted_event
    )

    record = run_once_stocks.run_once(symbols=["VOO"])

    assert record["symbols"]["VOO"]["risk_decision"]["type"] == "OrderEvent"
    assert record["symbols"]["VOO"]["execution_result"]["type"] == "SubmittedEvent"
    assert record["symbols"]["VOO"]["execution_result"]["order_id"] == "order-1"


def test_run_once_records_fetch_failure_without_aborting_other_symbols(tmp_path, monkeypatch):
    _patch_common(monkeypatch, tmp_path)

    def _fetch_latest_daily_bars(symbol):
        if symbol == "VOO":
            raise ConnectionError("模擬網路逾時")
        return _make_ohlcv_dataframe()

    monkeypatch.setattr(
        run_once_stocks.stock_data_agent, "fetch_latest_daily_bars", _fetch_latest_daily_bars
    )
    monkeypatch.setattr(
        run_once_stocks.signal_agent,
        "decide",
        lambda ohlcv_dataframe, symbol: _make_signal_event(symbol, 0),
    )
    monkeypatch.setattr(
        run_once_stocks.alpaca_paper_trading_client,
        "get_account",
        lambda: {"equity": 10_000.0, "cash": 10_000.0},
    )
    monkeypatch.setattr(run_once_stocks.alpaca_paper_trading_client, "get_positions", lambda: {})
    monkeypatch.setattr(
        run_once_stocks.risk_agent, "review_portfolio", lambda *args, **kwargs: {"QQQ": None}
    )

    record = run_once_stocks.run_once(symbols=["VOO", "QQQ"])

    assert "模擬網路逾時" in record["fetch_failures"]["VOO"]
    assert "VOO" not in record["symbols"]
    assert record["symbols"]["QQQ"]["risk_decision"]["type"] == "NoActionNeeded"
