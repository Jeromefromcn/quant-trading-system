"""run_once.py 的編排邏輯測試 — monkeypatch 掉所有 agent 與外部狀態, 只驗證串接順序與紀錄格式正確"""
import json
from datetime import datetime, timezone

import pandas as pd
import pytest

import run_once
from events import FillEvent, OrderEvent, SignalEvent


def _make_ohlcv_dataframe():
    """造一份足夠通過數據異常保護檢查的假 OHLCV 數據(open_time 為現在時間, 視為新鮮)"""
    current_time = pd.Timestamp.now(tz="UTC").tz_localize(None)
    return pd.DataFrame(
        {
            "open_time": [current_time],
            "open": [50_000.0],
            "high": [50_100.0],
            "low": [49_900.0],
            "close": [50_000.0],
            "volume": [10.0],
        }
    )


def _make_signal_event(symbol: str, target_position: int) -> SignalEvent:
    return SignalEvent(
        symbol=symbol,
        target_position=target_position,
        as_of_timestamp=datetime(2026, 7, 6, tzinfo=timezone.utc),
        latest_close_price=50_000.0,
        latest_average_true_range=1_000.0,
    )


def _patch_common(monkeypatch, tmp_path):
    """幾乎每個測試都需要的共用 monkeypatch: 記錄檔與每日狀態檔路徑指到 tmp_path, 並攔截 Telegram 警報"""
    monkeypatch.setattr(run_once, "LOG_FILE_PATH", str(tmp_path / "run_log.jsonl"))
    monkeypatch.setattr(run_once, "DAILY_STATE_FILE_PATH", str(tmp_path / "daily_risk_state.json"))
    monkeypatch.setattr(run_once.telegram_alerts, "send_alert", lambda message: None)


def test_run_once_logs_no_action_when_risk_agent_returns_none(tmp_path, monkeypatch):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        run_once.data_agent, "fetch_latest_candles", lambda symbol: _make_ohlcv_dataframe()
    )
    monkeypatch.setattr(
        run_once.signal_agent, "decide", lambda ohlcv_dataframe, symbol: _make_signal_event(symbol, 0)
    )
    monkeypatch.setattr(
        run_once.binance_testnet_client,
        "get_account_balances",
        lambda: {"BTC": 0.0, "USDT": 10_000.0},
    )
    monkeypatch.setattr(
        run_once.risk_agent, "review_portfolio", lambda *args, **kwargs: {"BTCUSDT": None}
    )

    record = run_once.run_once(symbols=["BTCUSDT"])

    assert record["symbols"]["BTCUSDT"]["risk_decision"]["type"] == "NoActionNeeded"
    assert record["symbols"]["BTCUSDT"]["execution_result"] is None


def test_run_once_executes_order_when_risk_agent_approves(tmp_path, monkeypatch):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        run_once.data_agent, "fetch_latest_candles", lambda symbol: _make_ohlcv_dataframe()
    )
    monkeypatch.setattr(
        run_once.signal_agent, "decide", lambda ohlcv_dataframe, symbol: _make_signal_event(symbol, 1)
    )
    monkeypatch.setattr(
        run_once.binance_testnet_client,
        "get_account_balances",
        lambda: {"BTC": 0.0, "USDT": 10_000.0},
    )
    approved_order = OrderEvent(symbol="BTCUSDT", side="BUY", quantity=0.05)
    monkeypatch.setattr(
        run_once.risk_agent, "review_portfolio", lambda *args, **kwargs: {"BTCUSDT": approved_order}
    )
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

    record = run_once.run_once(symbols=["BTCUSDT"])

    assert record["symbols"]["BTCUSDT"]["risk_decision"]["type"] == "OrderEvent"
    assert record["symbols"]["BTCUSDT"]["execution_result"]["type"] == "FillEvent"
    assert record["symbols"]["BTCUSDT"]["execution_result"]["order_id"] == "123"


def test_run_once_records_fetch_failure_without_aborting_other_symbols(tmp_path, monkeypatch):
    """
    與 Slice 1 不同: 單一標的抓取失敗只記錄該標的失敗, 不中止整個執行, 其他標的仍正常繼續
    (見設計文件錯誤處理段落: 多標的獨立管線, 一個標的失敗不影響另一個標的)
    """
    _patch_common(monkeypatch, tmp_path)

    def _fetch_latest_candles(symbol):
        if symbol == "BTCUSDT":
            raise ConnectionError("模擬網路逾時")
        return _make_ohlcv_dataframe()

    monkeypatch.setattr(run_once.data_agent, "fetch_latest_candles", _fetch_latest_candles)
    monkeypatch.setattr(
        run_once.signal_agent, "decide", lambda ohlcv_dataframe, symbol: _make_signal_event(symbol, 0)
    )
    monkeypatch.setattr(
        run_once.binance_testnet_client,
        "get_account_balances",
        lambda: {"BTC": 0.0, "ETH": 0.0, "USDT": 10_000.0},
    )
    monkeypatch.setattr(
        run_once.risk_agent, "review_portfolio", lambda *args, **kwargs: {"ETHUSDT": None}
    )

    record = run_once.run_once(symbols=["BTCUSDT", "ETHUSDT"])

    assert "模擬網路逾時" in record["fetch_failures"]["BTCUSDT"]
    assert "BTCUSDT" not in record["symbols"]
    assert record["symbols"]["ETHUSDT"]["risk_decision"]["type"] == "NoActionNeeded"

    with open(tmp_path / "run_log.jsonl", encoding="utf-8") as log_file:
        logged_record = json.loads(log_file.readline())
    assert "模擬網路逾時" in logged_record["fetch_failures"]["BTCUSDT"]
