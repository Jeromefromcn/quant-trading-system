"""risk_agent 的單元測試 — 涵蓋三種結果分支: 無動作, 核准下單(買/賣) , 風控擋下"""
from datetime import datetime, timezone

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
