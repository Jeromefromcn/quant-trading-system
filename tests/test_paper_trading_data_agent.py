"""data_agent.fetch_latest_candles 的單元測試: monkeypatch 掉真實網路請求, 只測試組裝與長度檢查邏輯"""
import pandas as pd
import pytest

import data_agent


def _make_raw_kline(open_time_milliseconds, close_time_milliseconds):
    return [
        open_time_milliseconds, "100.0", "101.0", "99.0", "100.0", "10.0",
        close_time_milliseconds, "1000.0", 5, "5.0", "500.0", "0",
    ]


def test_fetch_latest_candles_returns_requested_length(monkeypatch):
    interval_milliseconds = 86_400_000
    # 建構 11 根日線: 前 10 根已收盤(收盤時間在過去) , 最後一根尚未收盤(收盤時間在未來)
    now_milliseconds = int(pd.Timestamp.now("UTC").timestamp() * 1000)
    first_open_milliseconds = now_milliseconds - 10 * interval_milliseconds
    raw_klines = []
    for index in range(11):
        open_milliseconds = first_open_milliseconds + index * interval_milliseconds
        close_milliseconds = open_milliseconds + interval_milliseconds - 1
        raw_klines.append(_make_raw_kline(open_milliseconds, close_milliseconds))

    recorded_calls = []

    def _fake_request_klines_batch(symbol, interval, limit):
        recorded_calls.append({"symbol": symbol, "interval": interval, "limit": limit})
        return raw_klines

    monkeypatch.setattr(data_agent, "request_klines_batch", _fake_request_klines_batch)

    ohlcv_dataframe = data_agent.fetch_latest_candles("BTCUSDT", lookback_bars=10)

    assert len(ohlcv_dataframe) == 10
    assert list(ohlcv_dataframe.columns) == [
        "open_time", "open", "high", "low", "close", "volume",
    ]
    # 驗證 limit 契約: lookback_bars=10 時應多要一根(11) , 才能在丟棄未收盤最後一根後仍保留 10 根
    assert recorded_calls == [{"symbol": "BTCUSDT", "interval": "1d", "limit": 11}]


def test_fetch_latest_candles_raises_when_insufficient_bars(monkeypatch):
    interval_milliseconds = 86_400_000
    raw_klines = [
        _make_raw_kline(day * interval_milliseconds, day * interval_milliseconds + interval_milliseconds - 1)
        for day in range(5)
    ]

    recorded_calls = []

    def _fake_request_klines_batch(symbol, interval, limit):
        recorded_calls.append({"symbol": symbol, "interval": interval, "limit": limit})
        return raw_klines

    monkeypatch.setattr(data_agent, "request_klines_batch", _fake_request_klines_batch)

    with pytest.raises(ValueError, match="少於暖身所需"):
        data_agent.fetch_latest_candles("BTCUSDT", lookback_bars=10)

    # 驗證 limit 契約: lookback_bars=10 時應多要一根(11) , 即使結果不足也要先確認請求參數正確
    assert recorded_calls == [{"symbol": "BTCUSDT", "interval": "1d", "limit": 11}]
