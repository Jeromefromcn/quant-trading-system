"""risk_agent 的單元測試 — 涵蓋三種結果分支: 無動作, 核准下單(買/賣) , 風控擋下"""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import risk_agent
from events import OrderEvent, RejectionEvent, SignalEvent

ENGINE_PARAMETERS = {
    "initial_capital": 10_000.0,
    "risk_per_trade_percentage": 0.01,
    "atr_stop_multiplier": 2.0,
    "max_position_fraction": 1.0,
}


def _make_signal_event(
    target_position: int, close_price: float = 50_000.0, average_true_range: float = 1_000.0
) -> SignalEvent:
    return SignalEvent(
        symbol="BTCUSDT",
        target_position=target_position,
        as_of_timestamp=datetime(2026, 7, 6, tzinfo=timezone.utc),
        latest_close_price=close_price,
        latest_average_true_range=average_true_range,
    )


def test_determine_current_position_flat_when_below_dust_threshold():
    assert risk_agent.determine_current_position(0.0001, 50_000.0) == 0  # 市值 5 USDT, 低於 10 門檻


def test_determine_current_position_long_when_above_dust_threshold():
    assert risk_agent.determine_current_position(0.001, 50_000.0) == 1  # 市值 50 USDT, 高於 10 門檻


def test_determine_current_position_exactly_at_dust_threshold_is_long():
    assert risk_agent.determine_current_position(0.0002, 50_000.0) == 1  # 市值剛好 10 USDT, 達門檻視為多單


def test_check_max_loss_per_trade_passes_within_cap():
    assert risk_agent.check_max_loss_per_trade(
        order_quantity=0.03,
        average_true_range=1_000.0,
        atr_stop_multiplier=2.0,
        account_equity_usdt=10_000.0,
        max_loss_per_trade_fraction=0.015,
    ) is True  # 潛在虧損 = 0.03 * 2 * 1000 = 60, 上限 = 10000 * 0.015 = 150


def test_check_max_loss_per_trade_passes_at_exact_boundary():
    assert risk_agent.check_max_loss_per_trade(
        order_quantity=0.075,
        average_true_range=1_000.0,
        atr_stop_multiplier=2.0,
        account_equity_usdt=10_000.0,
        max_loss_per_trade_fraction=0.015,
    ) is True  # 潛在虧損 = 0.075 * 2 * 1000 = 150, 剛好等於上限 150


def test_check_max_loss_per_trade_rejects_when_exceeding_cap():
    assert risk_agent.check_max_loss_per_trade(
        order_quantity=0.1,
        average_true_range=1_000.0,
        atr_stop_multiplier=2.0,
        account_equity_usdt=10_000.0,
        max_loss_per_trade_fraction=0.015,
    ) is False  # 潛在虧損 = 0.1 * 2 * 1000 = 200, 超過上限 150


def test_check_daily_circuit_breaker_passes_when_no_loss():
    assert risk_agent.check_daily_circuit_breaker(10_000.0, 10_000.0, 0.04) is True


def test_check_daily_circuit_breaker_passes_at_exact_boundary():
    assert risk_agent.check_daily_circuit_breaker(9_600.0, 10_000.0, 0.04) is True  # 虧損剛好 4%


def test_check_daily_circuit_breaker_rejects_when_exceeding_threshold():
    assert risk_agent.check_daily_circuit_breaker(9_500.0, 10_000.0, 0.04) is False  # 虧損 5%


def test_check_max_concurrent_positions_passes_below_cap():
    assert risk_agent.check_max_concurrent_positions(1, "crypto", {"crypto": 3, "stocks": 5}) is True


def test_check_max_concurrent_positions_passes_just_below_cap():
    assert risk_agent.check_max_concurrent_positions(2, "crypto", {"crypto": 3, "stocks": 5}) is True


def test_check_max_concurrent_positions_rejects_at_cap():
    assert risk_agent.check_max_concurrent_positions(3, "crypto", {"crypto": 3, "stocks": 5}) is False


def test_review_returns_none_when_target_matches_current():
    signal_event = _make_signal_event(target_position=0)

    result = risk_agent.review(signal_event, 0.0, 10_000.0, ENGINE_PARAMETERS)

    assert result is None


def test_review_returns_sell_order_closing_full_position():
    signal_event = _make_signal_event(target_position=0)

    result = risk_agent.review(signal_event, 0.05, 10_000.0, ENGINE_PARAMETERS)

    assert isinstance(result, OrderEvent)
    assert result.side == "SELL"
    assert result.quantity == 0.05


def test_review_returns_buy_order_within_risk_cap():
    signal_event = _make_signal_event(target_position=1, close_price=50_000.0, average_true_range=1_000.0)

    result = risk_agent.review(signal_event, 0.0, 10_000.0, ENGINE_PARAMETERS)

    assert isinstance(result, OrderEvent)
    assert result.side == "BUY"
    # 佔比 = 1% * 50000 / (2 * 1000) = 0.25, 部位金額 = 10000 * 0.25 = 2500 USDT, 數量 = 2500/50000 = 0.05
    assert result.quantity == pytest.approx(0.05)


def test_review_rejects_buy_when_notional_exceeds_cap():
    # 用比較小的 initial_capital 讓風控上限低於算出的買進金額, 觸發 RejectionEvent
    signal_event = _make_signal_event(target_position=1, close_price=50_000.0, average_true_range=1_000.0)
    small_cap_engine_parameters = dict(ENGINE_PARAMETERS, initial_capital=1_000.0)

    result = risk_agent.review(signal_event, 0.0, 10_000.0, small_cap_engine_parameters)

    assert isinstance(result, RejectionEvent)
    assert "超過風控上限" in result.reason


def test_check_correlation_limit_passes_when_no_existing_positions():
    candidate_close_prices = pd.Series([100.0, 101.0, 102.0])
    assert risk_agent.check_correlation_limit(candidate_close_prices, {}) is True


def test_check_correlation_limit_passes_when_returns_are_negatively_correlated():
    # candidate 與 existing 每一步漲跌方向都相反, 相關係數應明顯為負, 遠低於 0.8 上限
    candidate_close_prices = pd.Series([100.0, 110.0, 100.0, 110.0, 100.0, 110.0])
    existing_close_prices = pd.Series([100.0, 90.0, 100.0, 90.0, 100.0, 90.0])
    assert risk_agent.check_correlation_limit(
        candidate_close_prices, {"ETHUSDT": existing_close_prices}, max_correlation=0.8
    ) is True


def test_check_correlation_limit_rejects_when_perfectly_correlated():
    candidate_close_prices = pd.Series([100.0, 102.0, 99.0, 105.0, 110.0])
    existing_close_prices = candidate_close_prices * 2.0  # 純比例縮放, 報酬率與 candidate 完全相同
    assert risk_agent.check_correlation_limit(
        candidate_close_prices, {"ETHUSDT": existing_close_prices}, max_correlation=0.8
    ) is False


def test_check_correlation_limit_rejects_when_insufficient_overlap():
    candidate_close_prices = pd.Series([100.0, 101.0])  # pct_change 後只剩 1 個數據點
    existing_close_prices = pd.Series([100.0, 101.0])
    assert risk_agent.check_correlation_limit(
        candidate_close_prices, {"ETHUSDT": existing_close_prices}, max_correlation=0.8
    ) is False


def test_check_data_staleness_passes_when_within_threshold():
    current_time = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    last_candle_open_time = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)  # 24 小時前開盤
    assert risk_agent.check_data_staleness(
        last_candle_open_time, current_time, timedelta(days=1), 1.5
    ) is True


def test_check_data_staleness_passes_at_exact_boundary():
    current_time = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    last_candle_open_time = datetime(2026, 7, 4, 0, 0, tzinfo=timezone.utc)
    # 約略收盤時間 = 開盤 + 1 天 = 2026-07-05 00:00, 距今 1.5 天, 剛好等於門檻
    assert risk_agent.check_data_staleness(
        last_candle_open_time, current_time, timedelta(days=1), 1.5
    ) is True


def test_check_data_staleness_rejects_when_beyond_threshold():
    current_time = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    last_candle_open_time = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)  # 3 天前開盤
    assert risk_agent.check_data_staleness(
        last_candle_open_time, current_time, timedelta(days=1), 1.5
    ) is False
