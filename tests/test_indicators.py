"""
指標庫單元測試: 驗證趨勢, 波動率, 動量指標的行為與數學性質, 而非實作細節
"""

import numpy as np
import pandas as pd
import pytest

from momentum import (
    moving_average_convergence_divergence,
    rate_of_change,
    relative_strength_index,
)
from trend import (
    average_directional_index,
    exponential_moving_average,
    simple_moving_average,
)
from volatility import average_true_range, rolling_volatility, true_range


@pytest.fixture
def trending_up_ohlcv():
    """一段穩定上漲的 OHLCV 數據, 用來檢驗指標在明確趨勢下的行為"""
    close_price = pd.Series(np.linspace(100, 200, 120))
    high_price = close_price + 2
    low_price = close_price - 2
    return pd.DataFrame(
        {
            "open": close_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": pd.Series(np.full(120, 1000.0)),
        }
    )


def test_simple_moving_average_equals_rolling_mean(trending_up_ohlcv):
    close_price = trending_up_ohlcv["close"]
    expected = close_price.rolling(window=20).mean()
    pd.testing.assert_series_equal(simple_moving_average(close_price, 20), expected)


def test_exponential_moving_average_tracks_price_closer_than_sma(trending_up_ohlcv):
    # EMA 對近期價格更敏感, 在上漲趨勢中應比同週期 SMA 更貼近收盤價
    close_price = trending_up_ohlcv["close"]
    ema = exponential_moving_average(close_price, 20)
    sma = simple_moving_average(close_price, 20)
    ema_deviation = (close_price - ema).abs().tail(30).mean()
    sma_deviation = (close_price - sma).abs().tail(30).mean()
    assert ema_deviation < sma_deviation


def test_true_range_is_non_negative(trending_up_ohlcv):
    computed_true_range = true_range(
        trending_up_ohlcv["high"],
        trending_up_ohlcv["low"],
        trending_up_ohlcv["close"],
    )
    assert (computed_true_range.dropna() >= 0).all()


def test_average_true_range_rises_with_volatility():
    # 波動放大的後半段, ATR 應明顯高於平穩的前半段
    calm_close = pd.Series(100 + np.zeros(60))
    volatile_close = pd.Series(100 + np.tile([5.0, -5.0], 30))
    close_price = pd.concat([calm_close, volatile_close], ignore_index=True)
    high_price = close_price + 1
    low_price = close_price - 1
    atr = average_true_range(high_price, low_price, close_price, period=14)
    assert atr.iloc[-1] > atr.iloc[59]


def test_rolling_volatility_is_non_negative(trending_up_ohlcv):
    volatility_series = rolling_volatility(trending_up_ohlcv["close"], period=14)
    assert (volatility_series.dropna() >= 0).all()


def test_relative_strength_index_stays_within_bounds(trending_up_ohlcv):
    rsi = relative_strength_index(trending_up_ohlcv["close"], period=14).dropna()
    assert rsi.between(0, 100).all()


def test_relative_strength_index_high_in_uptrend(trending_up_ohlcv):
    # 持續上漲時幾乎沒有下跌幅度, RSI 應趨近 100 而非中性的 50
    rsi = relative_strength_index(trending_up_ohlcv["close"], period=14)
    assert rsi.iloc[-1] > 70


def test_rate_of_change_positive_in_uptrend(trending_up_ohlcv):
    roc = rate_of_change(trending_up_ohlcv["close"], period=10).dropna()
    assert (roc > 0).all()


def test_macd_histogram_equals_line_minus_signal(trending_up_ohlcv):
    macd_frame = moving_average_convergence_divergence(trending_up_ohlcv["close"])
    reconstructed_histogram = macd_frame["macd_line"] - macd_frame["signal_line"]
    pd.testing.assert_series_equal(
        macd_frame["histogram"], reconstructed_histogram, check_names=False
    )


def test_average_directional_index_stays_within_bounds(trending_up_ohlcv):
    adx = average_directional_index(
        trending_up_ohlcv["high"],
        trending_up_ohlcv["low"],
        trending_up_ohlcv["close"],
        period=14,
    ).dropna()
    assert adx.between(0, 100).all()


def test_average_directional_index_high_in_strong_trend(trending_up_ohlcv):
    # 單邊上漲是最明確的趨勢, ADX 應偏高(遠高於常用的 25 門檻)
    adx = average_directional_index(
        trending_up_ohlcv["high"],
        trending_up_ohlcv["low"],
        trending_up_ohlcv["close"],
        period=14,
    )
    assert adx.iloc[-1] > 25
