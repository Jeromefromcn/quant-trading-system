"""
波動率指標庫: 衡量市場波動程度的向量化指標函數
所有函數只依賴 pandas, 全部向量化, 無 for loop, 無逐列 if-else
可被策略層與回測引擎重複引用, 與 01_learning 的教學腳本算法保持一致
"""

import pandas as pd


def true_range(
    high_price: pd.Series, low_price: pd.Series, close_price: pd.Series
) -> pd.Series:
    """
    True Range(真實波幅): 取三者最大值, 當天高低差, 當天最高與前一天收盤差, 當天最低與前一天收盤差
    納入前一天收盤是為了捕捉跳空(gap) , 只看當天高低差會低估隔夜跳空的風險
    """
    previous_close_price = close_price.shift(1)
    high_minus_low = high_price - low_price
    high_minus_previous_close = (high_price - previous_close_price).abs()
    low_minus_previous_close = (low_price - previous_close_price).abs()
    return pd.concat(
        [high_minus_low, high_minus_previous_close, low_minus_previous_close], axis=1
    ).max(axis=1)


def average_true_range(
    high_price: pd.Series,
    low_price: pd.Series,
    close_price: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    ATR(Average True Range, 平均真實波幅): True Range 的威爾德平滑(Wilder Smoothing)
    威爾德平滑等同於 alpha=1/period 的指數移動平均, 是 J. Welles Wilder 1978 年的原始定義
    """
    true_range_series = true_range(high_price, low_price, close_price)
    return true_range_series.ewm(alpha=1 / period, adjust=False).mean()


def rolling_volatility(close_price: pd.Series, period: int = 14) -> pd.Series:
    """
    滾動波動率: 過去 period 天每日報酬率(daily return) 的標準差, 最常見的波動率定義
    與 ATR 高度相關, 但以百分比報酬為單位, 不受價格絕對值影響, 便於跨資產比較
    """
    daily_return_percentage = close_price.pct_change()
    return daily_return_percentage.rolling(window=period).std()
