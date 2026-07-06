"""binance_fetcher.py 純解析邏輯的單元測試 — 不打真實網路請求, 用手造的假 K 線陣列驗證"""
import pandas as pd

from binance_fetcher import drop_unclosed_last_candle, parse_klines_to_ohlcv_dataframe


def _make_raw_kline(open_time_ms, close_time_ms, close_price="100.0"):
    """造一根 Binance 格式的原始 K 線陣列 (12 個無名欄位, 順序見 binance_fetcher.KLINE_COLUMNS) """
    return [
        open_time_ms, "100.0", "101.0", "99.0", close_price, "10.0",
        close_time_ms, "1000.0", 5, "5.0", "500.0", "0",
    ]


def test_parse_klines_to_ohlcv_dataframe_maps_core_columns():
    raw_klines = [
        _make_raw_kline(0, 86_399_999, "100.0"),
        _make_raw_kline(86_400_000, 172_799_999, "105.0"),
    ]
    ohlcv_dataframe = parse_klines_to_ohlcv_dataframe(raw_klines)
    assert list(ohlcv_dataframe["close"]) == [100.0, 105.0]
    assert ohlcv_dataframe["open_time"].iloc[0] == pd.Timestamp("1970-01-01")


def test_drop_unclosed_last_candle_removes_future_candle():
    far_future_open_ms = int(pd.Timestamp("2999-01-01").timestamp() * 1000)
    far_future_close_ms = far_future_open_ms + 86_399_999
    raw_klines = [
        _make_raw_kline(0, 86_399_999, "100.0"),
        _make_raw_kline(86_400_000, far_future_close_ms, "999.0"),
    ]
    ohlcv_dataframe = parse_klines_to_ohlcv_dataframe(raw_klines)
    trimmed_dataframe = drop_unclosed_last_candle(ohlcv_dataframe)
    assert len(trimmed_dataframe) == 1
    assert trimmed_dataframe["close"].iloc[0] == 100.0
    assert "close_time" not in trimmed_dataframe.columns


def test_drop_unclosed_last_candle_keeps_all_when_already_closed():
    raw_klines = [_make_raw_kline(0, 86_399_999, "100.0")]
    ohlcv_dataframe = parse_klines_to_ohlcv_dataframe(raw_klines)
    trimmed_dataframe = drop_unclosed_last_candle(ohlcv_dataframe)
    assert len(trimmed_dataframe) == 1
