"""run_once.py 的編排邏輯測試 — monkeypatch 掉所有 4 個 agent, 只驗證串接順序與紀錄格式正確"""
import json
from datetime import datetime, timezone

import pandas as pd
import pytest

import run_once
from events import FillEvent, OrderEvent, SignalEvent


def _make_signal_event(target_position: int) -> SignalEvent:
    return SignalEvent(
        symbol="BTCUSDT",
        target_position=target_position,
        as_of_timestamp=datetime(2026, 7, 6, tzinfo=timezone.utc),
        latest_close_price=50_000.0,
        latest_average_true_range=1_000.0,
    )


def test_run_once_logs_no_action_when_risk_agent_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(run_once, "LOG_FILE_PATH", str(tmp_path / "run_log.jsonl"))
    monkeypatch.setattr(run_once.data_agent, "fetch_latest_candles", lambda symbol: pd.DataFrame())
    monkeypatch.setattr(
        run_once.signal_agent, "decide", lambda ohlcv_dataframe, symbol: _make_signal_event(0)
    )
    monkeypatch.setattr(
        run_once.binance_testnet_client,
        "get_account_balances",
        lambda: {"BTC": 0.0, "USDT": 10_000.0},
    )
    monkeypatch.setattr(run_once.risk_agent, "review", lambda *args, **kwargs: None)

    record = run_once.run_once("BTCUSDT")

    assert record["risk_decision"]["type"] == "NoActionNeeded"
    assert record["execution_result"] is None


def test_run_once_executes_order_when_risk_agent_approves(tmp_path, monkeypatch):
    monkeypatch.setattr(run_once, "LOG_FILE_PATH", str(tmp_path / "run_log.jsonl"))
    monkeypatch.setattr(run_once.data_agent, "fetch_latest_candles", lambda symbol: pd.DataFrame())
    monkeypatch.setattr(
        run_once.signal_agent, "decide", lambda ohlcv_dataframe, symbol: _make_signal_event(1)
    )
    monkeypatch.setattr(
        run_once.binance_testnet_client,
        "get_account_balances",
        lambda: {"BTC": 0.0, "USDT": 10_000.0},
    )
    approved_order = OrderEvent(symbol="BTCUSDT", side="BUY", quantity=0.05)
    monkeypatch.setattr(run_once.risk_agent, "review", lambda *args, **kwargs: approved_order)
    monkeypatch.setattr(
        run_once.binance_testnet_client,
        "get_symbol_filters",
        lambda symbol: {"step_size": 0.0001, "min_notional": 10.0},
    )
    fill_event = FillEvent(
        symbol="BTCUSDT", side="BUY", quantity=0.05, average_price=50_000.0, order_id="123"
    )
    monkeypatch.setattr(
        run_once.execution_agent, "execute", lambda order_event, symbol_filters: fill_event
    )

    record = run_once.run_once("BTCUSDT")

    assert record["risk_decision"]["type"] == "OrderEvent"
    assert record["execution_result"]["type"] == "FillEvent"
    assert record["execution_result"]["order_id"] == "123"


def test_run_once_logs_and_reraises_when_data_agent_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(run_once, "LOG_FILE_PATH", str(tmp_path / "run_log.jsonl"))

    def _raise_connection_error(symbol):
        raise ConnectionError("模擬網路逾時")

    monkeypatch.setattr(run_once.data_agent, "fetch_latest_candles", _raise_connection_error)

    with pytest.raises(ConnectionError):
        run_once.run_once("BTCUSDT")

    with open(tmp_path / "run_log.jsonl", encoding="utf-8") as log_file:
        logged_record = json.loads(log_file.readline())
    assert "模擬網路逾時" in logged_record["pipeline_error"]
