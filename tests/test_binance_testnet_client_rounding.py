"""
binance_testnet_client 兩個純函數的單元測試: round_quantity_to_step_size 與 _format_quantity_for_request,
不打真實網路請求
"""
import pytest

import binance_testnet_client
from binance_testnet_client import round_quantity_to_step_size


def test_round_quantity_to_step_size_rounds_down_to_nearest_step():
    assert round_quantity_to_step_size(0.123456, 0.0001) == pytest.approx(0.1234)


def test_round_quantity_to_step_size_exact_multiple_unchanged():
    assert round_quantity_to_step_size(0.005, 0.001) == pytest.approx(0.005)


def test_round_quantity_to_step_size_none_step_size_returns_original_quantity():
    assert round_quantity_to_step_size(0.123456, None) == 0.123456


def test_round_quantity_to_step_size_produces_clean_float_no_binary_noise():
    result = round_quantity_to_step_size(0.123456, 0.0001)
    assert result == 0.1234
    assert str(result) == "0.1234"


def test_format_quantity_for_request_avoids_scientific_notation():
    assert binance_testnet_client._format_quantity_for_request(0.00004) == "0.00004"


def test_format_quantity_for_request_strips_trailing_zeros_from_whole_numbers():
    assert binance_testnet_client._format_quantity_for_request(2.0) == "2"


def test_format_quantity_for_request_keeps_significant_trailing_digit():
    assert binance_testnet_client._format_quantity_for_request(0.005) == "0.005"
