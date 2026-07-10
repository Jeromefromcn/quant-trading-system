"""
趨勢指標庫: 衡量價格趨勢方向與強度的向量化指標函數
所有函數只依賴 pandas 與 numpy, 全部向量化, 無 for loop, 無逐列 if-else
"""

import os
import sys

import numpy as np
import pandas as pd

# 目錄名以數字開頭無法當成 Python 套件, 因此把本目錄加入模組搜尋路徑, 才能引用同層的 volatility 模組
sys.path.insert(0, os.path.dirname(__file__))
from volatility import true_range


def simple_moving_average(close_price: pd.Series, period: int) -> pd.Series:
    """
    SMA(Simple Moving Average, 簡單移動平均線): 過去 period 天收盤價的算術平均, 每天權重相同
    """
    return close_price.rolling(window=period).mean()


def exponential_moving_average(close_price: pd.Series, span: int) -> pd.Series:
    """
    EMA(Exponential Moving Average, 指數移動平均線): 越接近今天權重越高, 對近期價格反應較快
    adjust=False 代表用遞迴公式逐天計算, 是業界計算 EMA 的慣用設定
    """
    return close_price.ewm(span=span, adjust=False).mean()


def average_directional_index(
    high_price: pd.Series,
    low_price: pd.Series,
    close_price: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    ADX(Average Directional Index, 平均趨向指標): 衡量趨勢的強度, 不區分方向, 範圍 0 到 100
    常用門檻: ADX > 25 代表趨勢明確, 適合趨勢跟蹤策略進場; ADX 偏低代表盤整, 均線交叉容易產生假信號
    算法(J. Welles Wilder 1978) : 由 +DM / -DM(方向性移動) 與 True Range 經威爾德平滑後推導
    """
    previous_high_price = high_price.shift(1)
    previous_low_price = low_price.shift(1)
    upward_move = high_price - previous_high_price
    downward_move = previous_low_price - low_price

    # +DM(Positive Directional Movement, 正向移動) : 上漲動能大於下跌動能且為正時才計入, 否則為 0
    positive_directional_movement = np.where(
        (upward_move > downward_move) & (upward_move > 0), upward_move, 0.0
    )
    # -DM(Negative Directional Movement, 負向移動) : 下跌動能大於上漲動能且為正時才計入, 否則為 0
    negative_directional_movement = np.where(
        (downward_move > upward_move) & (downward_move > 0), downward_move, 0.0
    )

    # 用威爾德平滑(Wilder Smoothing, alpha=1/period 的 EMA) 分別平滑 TR, +DM, -DM
    wilder_smoothing_alpha = 1 / period
    smoothed_true_range = (
        true_range(high_price, low_price, close_price)
        .ewm(alpha=wilder_smoothing_alpha, adjust=False)
        .mean()
    )
    smoothed_positive_movement = (
        pd.Series(positive_directional_movement, index=high_price.index)
        .ewm(alpha=wilder_smoothing_alpha, adjust=False)
        .mean()
    )
    smoothed_negative_movement = (
        pd.Series(negative_directional_movement, index=high_price.index)
        .ewm(alpha=wilder_smoothing_alpha, adjust=False)
        .mean()
    )

    # +DI / -DI(Directional Indicator, 方向指標) : 方向性移動佔真實波幅的比例, 以百分比表示
    positive_directional_indicator = 100 * smoothed_positive_movement / smoothed_true_range
    negative_directional_indicator = 100 * smoothed_negative_movement / smoothed_true_range

    # DX(Directional Index, 趨向指標) : +DI 與 -DI 的分歧程度, 分歧越大代表方向越明確
    directional_indicator_sum = (
        positive_directional_indicator + negative_directional_indicator
    )
    directional_index = (
        100
        * (positive_directional_indicator - negative_directional_indicator).abs()
        / directional_indicator_sum.replace(0, np.nan)
    )
    # ADX 是 DX 再做一次威爾德平滑, 過濾掉單日噪音, 得到平穩的趨勢強度曲線
    return directional_index.ewm(alpha=wilder_smoothing_alpha, adjust=False).mean()
