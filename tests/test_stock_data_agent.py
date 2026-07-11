"""stock_data_agent.fetch_latest_daily_bars 的單元測試: monkeypatch 掉真實網路請求, 只測組裝與長度檢查邏輯"""
import pandas as pd
import pytest

import stock_data_agent


def _make_ohlcv_dataframe(number_of_rows: int) -> pd.DataFrame:
    base_time = pd.Timestamp("2026-01-01")
    return pd.DataFrame(
        {
            "open_time": [base_time + pd.Timedelta(days=index) for index in range(number_of_rows)],
            "open": [100.0] * number_of_rows,
            "high": [101.0] * number_of_rows,
            "low": [99.0] * number_of_rows,
            "close": [100.0 + index for index in range(number_of_rows)],
            "volume": [1_000_000.0] * number_of_rows,
        }
    )


def test_fetch_latest_daily_bars_returns_last_lookback_bars_rows(monkeypatch):
    recorded_calls = []

    def _fake_fetch_full_history_daily_bars(symbol, start_date=None, data_feed="iex"):
        recorded_calls.append({"symbol": symbol, "start_date": start_date})
        return _make_ohlcv_dataframe(150)

    monkeypatch.setattr(
        stock_data_agent, "fetch_full_history_daily_bars", _fake_fetch_full_history_daily_bars
    )

    ohlcv_dataframe = stock_data_agent.fetch_latest_daily_bars("VOO", lookback_bars=100)

    assert len(ohlcv_dataframe) == 100
    assert list(ohlcv_dataframe.columns) == ["open_time", "open", "high", "low", "close", "volume"]
    # 保留的必須是最後 100 根(最新的), 不是前 100 根
    assert ohlcv_dataframe["close"].iloc[-1] == 100.0 + 149
    assert recorded_calls[0]["symbol"] == "VOO"


def test_fetch_latest_daily_bars_raises_when_insufficient_bars(monkeypatch):
    def _fake_fetch_full_history_daily_bars(symbol, start_date=None, data_feed="iex"):
        return _make_ohlcv_dataframe(5)

    monkeypatch.setattr(
        stock_data_agent, "fetch_full_history_daily_bars", _fake_fetch_full_history_daily_bars
    )

    with pytest.raises(ValueError, match="少於暖身所需"):
        stock_data_agent.fetch_latest_daily_bars("VOO", lookback_bars=100)
