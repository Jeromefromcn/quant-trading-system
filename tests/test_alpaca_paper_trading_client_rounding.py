"""alpaca_paper_trading_client 的純函數單元測試: round_quantity_down_to_whole_shares, 不打真實網路請求"""
import alpaca_paper_trading_client


def test_round_quantity_down_to_whole_shares_truncates_fraction():
    assert alpaca_paper_trading_client.round_quantity_down_to_whole_shares(10.9) == 10


def test_round_quantity_down_to_whole_shares_exact_whole_number_unchanged():
    assert alpaca_paper_trading_client.round_quantity_down_to_whole_shares(7.0) == 7


def test_round_quantity_down_to_whole_shares_below_one_share_becomes_zero():
    assert alpaca_paper_trading_client.round_quantity_down_to_whole_shares(0.5) == 0
