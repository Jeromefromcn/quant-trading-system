"""binance_testnet_client.round_quantity_to_step_size 的單元測試 — 純函數, 不打真實網路請求"""
import pytest

from binance_testnet_client import round_quantity_to_step_size


def test_round_quantity_to_step_size_rounds_down_to_nearest_step():
    assert round_quantity_to_step_size(0.123456, 0.0001) == pytest.approx(0.1234)


def test_round_quantity_to_step_size_exact_multiple_unchanged():
    assert round_quantity_to_step_size(0.005, 0.001) == pytest.approx(0.005)


def test_round_quantity_to_step_size_none_step_size_returns_original_quantity():
    assert round_quantity_to_step_size(0.123456, None) == 0.123456
