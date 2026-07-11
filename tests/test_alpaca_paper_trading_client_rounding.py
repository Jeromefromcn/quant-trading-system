"""
alpaca_paper_trading_client 的純函數單元測試: round_quantity_down_to_whole_shares,
round_price_to_cent, 不打真實網路請求
"""
import alpaca_paper_trading_client


def test_round_quantity_down_to_whole_shares_truncates_fraction():
    assert alpaca_paper_trading_client.round_quantity_down_to_whole_shares(10.9) == 10


def test_round_quantity_down_to_whole_shares_exact_whole_number_unchanged():
    assert alpaca_paper_trading_client.round_quantity_down_to_whole_shares(7.0) == 7


def test_round_quantity_down_to_whole_shares_below_one_share_becomes_zero():
    assert alpaca_paper_trading_client.round_quantity_down_to_whole_shares(0.5) == 0


def test_round_price_to_cent_rounds_to_two_decimals():
    assert alpaca_paper_trading_client.round_price_to_cent(725.595) == 725.6


def test_round_price_to_cent_leaves_exact_cent_unchanged():
    assert alpaca_paper_trading_client.round_price_to_cent(550.25) == 550.25


def test_round_price_to_cent_rounds_down_when_third_decimal_is_below_five():
    assert alpaca_paper_trading_client.round_price_to_cent(550.254) == 550.25
