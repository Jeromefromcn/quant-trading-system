"""
風控與倉位計算單元測試: 驗證固定風險倉位法的核心性質
固定風險的定義: 不論波動大小, 每筆交易萬一打到止損, 虧損金額都固定佔賬戶同一比例
"""

import numpy as np
import pandas as pd

from engine import compute_position_fraction


def test_position_fraction_shrinks_when_volatility_rises():
    # ATR 越大(波動越大) , 算出的倉位佔比應越小, 才能維持單筆風險固定
    close_price = pd.Series([100.0, 100.0])
    low_volatility_atr = pd.Series([1.0, 1.0])
    high_volatility_atr = pd.Series([5.0, 5.0])
    low_volatility_fraction = compute_position_fraction(
        close_price, low_volatility_atr, 0.01, 2.0, max_position_fraction=1.0
    )
    high_volatility_fraction = compute_position_fraction(
        close_price, high_volatility_atr, 0.01, 2.0, max_position_fraction=1.0
    )
    assert (high_volatility_fraction < low_volatility_fraction).all()


def test_position_fraction_keeps_risk_amount_constant():
    # 固定風險的驗證: 倉位單位數 × 止損距離 應等於賬戶 × 每筆風險比例, 與 ATR 無關
    account_size = 10_000.0
    risk_percentage = 0.01
    atr_stop_multiplier = 2.0
    close_price = pd.Series([100.0, 100.0])
    average_true_range_series = pd.Series([1.0, 4.0])

    position_fraction = compute_position_fraction(
        close_price,
        average_true_range_series,
        risk_percentage,
        atr_stop_multiplier,
        max_position_fraction=1.0,
    )
    position_value = position_fraction * account_size
    position_units = position_value / close_price
    stop_loss_distance = atr_stop_multiplier * average_true_range_series
    risk_amount = position_units * stop_loss_distance

    expected_risk_amount = account_size * risk_percentage
    assert np.allclose(risk_amount, expected_risk_amount)


def test_position_fraction_respects_maximum_cap():
    # 極低波動下理論佔比會超過 1, 必須被上限夾住, 避免現貨出現槓桿倉位
    close_price = pd.Series([100.0])
    tiny_atr = pd.Series([0.01])
    position_fraction = compute_position_fraction(
        close_price, tiny_atr, 0.01, 2.0, max_position_fraction=1.0
    )
    assert (position_fraction <= 1.0).all()
