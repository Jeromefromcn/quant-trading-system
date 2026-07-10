"""
趨勢跟蹤策略: EMA(Exponential Moving Average, 指數移動平均線) 雙均線交叉, 可選 ADX 趨勢強度過濾
進場邏輯: 快線在慢線之上代表多頭排列, 持有多單; 快線跌回慢線之下則空手
可選過濾: 加入 ADX(Average Directional Index, 平均趨向指標) 門檻, 只在趨勢明確時進場, 減少盤整市假信號
這是 Phase 2 第一輪要建立基準(baseline) 的策略, 對應 ROADMAP EMA 雙均線基準版
"""

import os
import sys

import pandas as pd

# 目錄名以數字開頭無法當成 Python 套件, 手動把策略層與指標層目錄加入模組搜尋路徑
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "01_indicators"))
from base import Strategy
from trend import average_directional_index, exponential_moving_average


class TrendFollowingStrategy(Strategy):
    """EMA 雙均線交叉趨勢跟蹤策略, 可選 ADX 過濾"""

    name = "trend_following_ema_crossover"

    def __init__(
        self,
        fast_span: int = 12,
        slow_span: int = 26,
        adx_period: int = 14,
        adx_threshold: float = 0.0,
    ) -> None:
        """
        參數 fast_span / slow_span: 快線與慢線的 EMA 週期
        參數 adx_period: 計算 ADX 的週期
        參數 adx_threshold: ADX 過濾門檻, 只有 ADX 高於此值才允許進場; 設為 0 等同不過濾(純均線交叉)
        """
        self.fast_span = fast_span
        self.slow_span = slow_span
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold

    def generate_signals(self, ohlcv_dataframe: pd.DataFrame) -> pd.Series:
        close_price = ohlcv_dataframe["close"]
        exponential_moving_average_fast = exponential_moving_average(
            close_price, self.fast_span
        )
        exponential_moving_average_slow = exponential_moving_average(
            close_price, self.slow_span
        )
        # 多頭排列: 快線在慢線之上, 用布林比較取代 if-else
        is_fast_above_slow = (
            exponential_moving_average_fast > exponential_moving_average_slow
        )

        # ADX 過濾: 趨勢強度需高於門檻; 門檻為 0 時此條件恆為真, 等同不過濾
        # ADX 前期因平滑尚未穩定會是 NaN, 與門檻比較會得到 False, 自然避免在數據不足時進場
        average_directional_index_series = average_directional_index(
            ohlcv_dataframe["high"],
            ohlcv_dataframe["low"],
            close_price,
            self.adx_period,
        )
        is_trend_strong_enough = average_directional_index_series > self.adx_threshold

        target_position = (is_fast_above_slow & is_trend_strong_enough).astype(int)
        return target_position

    def describe_parameters(self) -> dict:
        return {
            "fast_span": self.fast_span,
            "slow_span": self.slow_span,
            "adx_period": self.adx_period,
            "adx_threshold": self.adx_threshold,
        }
