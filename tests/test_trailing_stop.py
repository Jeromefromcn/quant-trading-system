"""
移動止損出場 (ATR trailing stop exit) 的行為測試 — 引擎新功能
語義 (見 STRATEGY_LOG / exp_004): 進場沿用策略信號上升緣, 出場改由移動止損接管並取代 EMA 出場;
止損被掃出後, 須等原始信號重新 0→1 才准再進場 (再進場鎖定); 關閉時引擎行為與原本逐位元一致.
用手工構造的確定價格序列精準定位「哪一根被交易」, 風格對齊 test_engine_invariants.py.
"""

import numpy as np
import pandas as pd
import pytest

from base import Strategy
from engine import BacktestEngine
from trend_following import TrendFollowingStrategy


def make_ohlcv(closes) -> pd.DataFrame:
    """由收盤價序列造出 OHLCV; high/low 取 ±1 的固定日內區間, 讓 ATR 行為可預期"""
    close_price = pd.Series(closes, dtype=float)
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2020-01-01", periods=len(close_price), freq="D"),
            "open": close_price,
            "high": close_price + 1.0,
            "low": close_price - 1.0,
            "close": close_price,
            "volume": pd.Series(np.full(len(close_price), 1000.0)),
        }
    )


class LongWindows(Strategy):
    """測試策略: 在指定的多個 [start, end) 區間輸出做多信號, 精準控制進出場信號的邊緣"""

    name = "long_windows"

    def __init__(self, windows) -> None:
        self.windows = windows

    def generate_signals(self, ohlcv_dataframe: pd.DataFrame) -> pd.Series:
        target_position = pd.Series(0, index=ohlcv_dataframe.index)
        for start, end in self.windows:
            target_position.iloc[start:end] = 1
        return target_position


def test_trailing_stop_exits_on_large_pullback_and_does_not_reenter():
    """大幅回落觸發移動止損出場; 信號雖整段為 1, 停損後無新上升緣 → 不得再進場, 只有一筆交易"""
    closes = [100.0] * 30 + list(np.linspace(105, 150, 10)) + [110.0] * 10
    ohlcv = make_ohlcv(closes)
    strategy = LongWindows([(30, len(closes))])
    engine = BacktestEngine(
        trailing_stop_atr_multiplier=3.0, fee_rate=0.0, slippage_rate=0.0
    )

    result = engine.run(ohlcv, strategy)

    assert len(result.trades) == 1
    # 崩盤後收盤 110, 出場價應落在崩盤區而非序列最後一根
    assert result.trades.iloc[0]["exit_price"] == pytest.approx(110.0)


def test_trailing_stop_does_not_exit_while_price_keeps_rising():
    """單調上漲時收盤永遠是新高, 止損線恆在收盤之下 → 不觸發, 持有到最後一根"""
    closes = [100.0] * 30 + list(np.linspace(101, 200, 40))
    ohlcv = make_ohlcv(closes)
    strategy = LongWindows([(30, len(closes))])
    engine = BacktestEngine(
        trailing_stop_atr_multiplier=3.0, fee_rate=0.0, slippage_rate=0.0
    )

    result = engine.run(ohlcv, strategy)

    assert len(result.trades) == 1
    assert result.trades.iloc[0]["exit_date"] == ohlcv["open_time"].iloc[-1]


def test_trailing_stop_holds_past_ema_exit_signal():
    """移動止損取代 EMA 出場: 信號在中途轉 0 但價格續漲未觸發止損時, 應持有到最後而非在信號轉 0 處出場"""
    closes = [100.0] * 30 + list(np.linspace(101, 200, 40))
    ohlcv = make_ohlcv(closes)
    strategy = LongWindows([(30, 40)])  # 信號僅 30..39 為 1, bar 40 起轉 0 (等同 EMA 下穿)

    with_trailing = BacktestEngine(
        trailing_stop_atr_multiplier=3.0, fee_rate=0.0, slippage_rate=0.0
    ).run(ohlcv, strategy)
    without_trailing = BacktestEngine(
        trailing_stop_atr_multiplier=None, fee_rate=0.0, slippage_rate=0.0
    ).run(ohlcv, strategy)

    # 關閉: 信號轉 0 於 bar 40 → 該處出場; 開啟: 忽略信號轉 0, 持有到最後
    assert (
        without_trailing.trades.iloc[0]["exit_date"]
        < with_trailing.trades.iloc[0]["exit_date"]
    )
    assert with_trailing.trades.iloc[0]["exit_date"] == ohlcv["open_time"].iloc[-1]


def test_trailing_stop_reenters_only_on_fresh_entry_signal():
    """停損掃出後, 唯有原始信號重新 0→1 才准第二次進場 → 兩段獨立行情產生兩筆交易"""
    closes = (
        [100.0] * 30
        + list(np.linspace(105, 150, 10))  # 30..39 上漲到峰值
        + [110.0] * 5  # 40..44 崩盤, 觸發止損
        + list(np.linspace(112, 160, 15))  # 45..59 回升
    )
    ohlcv = make_ohlcv(closes)
    # 信號 30..44 為 1 (含崩盤), 45..49 歸零, 50 起再度為 1 → 於 bar 50 產生新上升緣
    strategy = LongWindows([(30, 45), (50, len(closes))])
    engine = BacktestEngine(
        trailing_stop_atr_multiplier=3.0, fee_rate=0.0, slippage_rate=0.0
    )

    result = engine.run(ohlcv, strategy)

    assert len(result.trades) == 2


@pytest.mark.parametrize("truncation_point", [50, 120, 200, 350])
def test_no_future_data_leakage_with_trailing_stop(truncation_point):
    """前視偏差防護: 開啟移動止損後, 截斷未來數據不得改變截斷點之前的每日報酬 (路徑依賴邏輯最易漏這條)"""
    time_index = np.arange(400)
    close_price = 100 + 20 * np.sin(time_index / 15) + time_index * 0.05
    close_series = pd.Series(close_price)
    ohlcv = pd.DataFrame(
        {
            "open_time": pd.date_range("2020-01-01", periods=400, freq="D"),
            "open": close_series,
            "high": close_series + 1,
            "low": close_series - 1,
            "close": close_series,
            "volume": pd.Series(np.full(400, 1000.0)),
        }
    )
    strategy = TrendFollowingStrategy(fast_span=12, slow_span=26, adx_threshold=0.0)
    engine = BacktestEngine(trailing_stop_atr_multiplier=3.0)

    full_result = engine.run(ohlcv, strategy)
    truncated_result = engine.run(ohlcv.iloc[:truncation_point], strategy)

    pd.testing.assert_series_equal(
        truncated_result.daily_return_percentage.reset_index(drop=True),
        full_result.daily_return_percentage.iloc[:truncation_point].reset_index(
            drop=True
        ),
        check_names=False,
    )


def test_trailing_stop_disabled_is_identical_to_omitting_the_parameter():
    """向後相容: 明確傳 None 與完全不傳此參數, 淨值曲線必須逐值相同 (加參數不改變預設路徑)"""
    time_index = np.arange(400)
    close_price = 100 + 20 * np.sin(time_index / 15) + time_index * 0.05
    close_series = pd.Series(close_price)
    ohlcv = pd.DataFrame(
        {
            "open_time": pd.date_range("2020-01-01", periods=400, freq="D"),
            "open": close_series,
            "high": close_series + 1,
            "low": close_series - 1,
            "close": close_series,
            "volume": pd.Series(np.full(400, 1000.0)),
        }
    )
    strategy = TrendFollowingStrategy(fast_span=12, slow_span=26, adx_threshold=0.0)

    default_equity = BacktestEngine().run(ohlcv, strategy).equity_curve
    explicit_none_equity = (
        BacktestEngine(trailing_stop_atr_multiplier=None).run(ohlcv, strategy).equity_curve
    )

    pd.testing.assert_series_equal(default_equity, explicit_none_equity)
