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

RISK_LIMITS = {
    "max_loss_per_trade_fraction": 0.015,
    "max_daily_loss_fraction": 0.04,
    "max_positions_by_market": {"crypto": 3, "stocks": 5},
    "max_correlation": 0.8,
}


def _make_close_price_series(values):
    return pd.Series(values, dtype=float)


def _make_signal_event(
    symbol="BTCUSDT",
    target_position=1,
    close_price: float = 50_000.0,
    average_true_range: float = 1_000.0,
):
    return SignalEvent(
        symbol=symbol,
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


def test_check_correlation_limit_rejects_when_correlation_is_nan():
    # existing 持倉價格完全不變, 報酬率全為 0, 變異數為 0, 相關係數無法定義(NaN), 視為無法確認風險應拒絕
    candidate_close_prices = pd.Series([100.0, 102.0, 99.0, 105.0])
    existing_close_prices = pd.Series([100.0, 100.0, 100.0, 100.0])
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


def test_review_portfolio_circuit_breaker_rejects_all_symbols():
    signal_events = {
        "BTCUSDT": _make_signal_event("BTCUSDT", target_position=1),
        "ETHUSDT": _make_signal_event("ETHUSDT", target_position=0),
    }

    decisions = risk_agent.review_portfolio(
        signal_events, [], {}, 9_500.0, 10_000.0, {}, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["BTCUSDT"], RejectionEvent)
    assert "熔斷" in decisions["BTCUSDT"].reason
    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "熔斷" in decisions["ETHUSDT"].reason


def test_review_portfolio_marks_stale_symbol_as_rejected_and_other_proceeds():
    signal_events = {"BTCUSDT": _make_signal_event("BTCUSDT", target_position=0)}

    decisions = risk_agent.review_portfolio(
        signal_events, ["ETHUSDT"], {}, 10_000.0, 10_000.0, {}, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "過期" in decisions["ETHUSDT"].reason
    assert decisions["BTCUSDT"] is None


def test_review_portfolio_returns_sell_order_closing_full_position():
    signal_events = {"BTCUSDT": _make_signal_event("BTCUSDT", target_position=0)}

    decisions = risk_agent.review_portfolio(
        signal_events, [], {"BTCUSDT": 0.05}, 10_000.0, 10_000.0, {}, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["BTCUSDT"], OrderEvent)
    assert decisions["BTCUSDT"].side == "SELL"
    assert decisions["BTCUSDT"].quantity == 0.05


def test_review_portfolio_approves_buy_when_alone_and_within_limits():
    signal_events = {
        "BTCUSDT": _make_signal_event(
            "BTCUSDT", target_position=1, close_price=50_000.0, average_true_range=1_000.0
        )
    }
    close_price_histories = {
        "BTCUSDT": _make_close_price_series([50_000.0 + index * 100 for index in range(30)])
    }

    decisions = risk_agent.review_portfolio(
        signal_events, [], {}, 10_000.0, 10_000.0, close_price_histories, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["BTCUSDT"], OrderEvent)
    assert decisions["BTCUSDT"].side == "BUY"
    assert decisions["BTCUSDT"].quantity == pytest.approx(0.05)


def test_review_portfolio_rejects_second_correlated_open_in_same_batch():
    btc_close_prices = _make_close_price_series([50_000.0 + index * 100 for index in range(30)])
    eth_close_prices = btc_close_prices * 2.0  # 純比例縮放, 相關係數必為 1.0
    signal_events = {
        "BTCUSDT": _make_signal_event(
            "BTCUSDT", target_position=1, close_price=50_000.0, average_true_range=1_000.0
        ),
        "ETHUSDT": _make_signal_event(
            "ETHUSDT", target_position=1, close_price=3_000.0, average_true_range=100.0
        ),
    }
    close_price_histories = {"BTCUSDT": btc_close_prices, "ETHUSDT": eth_close_prices}

    decisions = risk_agent.review_portfolio(
        signal_events, [], {}, 10_000.0, 10_000.0, close_price_histories, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["BTCUSDT"], OrderEvent)  # 依固定順序先處理, 當時尚無現有持倉可比較
    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "相關係數" in decisions["ETHUSDT"].reason


def test_review_portfolio_rejects_buy_when_max_loss_per_trade_exceeded():
    signal_events = {
        "BTCUSDT": _make_signal_event(
            "BTCUSDT", target_position=1, close_price=50_000.0, average_true_range=1_000.0
        )
    }
    close_price_histories = {
        "BTCUSDT": _make_close_price_series([50_000.0 + index * 100 for index in range(30)])
    }
    strict_risk_limits = dict(RISK_LIMITS, max_loss_per_trade_fraction=0.005)

    decisions = risk_agent.review_portfolio(
        signal_events, [], {}, 10_000.0, 10_000.0, close_price_histories, ENGINE_PARAMETERS, strict_risk_limits
    )

    assert isinstance(decisions["BTCUSDT"], RejectionEvent)
    assert "潛在虧損" in decisions["BTCUSDT"].reason


def test_review_portfolio_rejects_buy_when_max_concurrent_positions_reached():
    signal_events = {
        "BTCUSDT": _make_signal_event(
            "BTCUSDT", target_position=1, close_price=50_000.0, average_true_range=1_000.0
        ),
        "ETHUSDT": _make_signal_event(
            "ETHUSDT", target_position=1, close_price=3_000.0, average_true_range=100.0
        ),
    }
    current_base_asset_balances = {"BTCUSDT": 0.05}  # 市值 2500 USDT, 已是真實持倉
    close_price_histories = {
        "BTCUSDT": _make_close_price_series([50_000.0 + index * 100 for index in range(30)]),
        "ETHUSDT": _make_close_price_series([3_000.0 + index * 10 for index in range(30)]),
    }
    strict_risk_limits = dict(RISK_LIMITS, max_positions_by_market={"crypto": 1, "stocks": 5})

    decisions = risk_agent.review_portfolio(
        signal_events, [], current_base_asset_balances, 12_500.0, 12_500.0,
        close_price_histories, ENGINE_PARAMETERS, strict_risk_limits,
    )

    assert decisions["BTCUSDT"] is None  # 已是多單, 目標與當前相同
    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "持倉數" in decisions["ETHUSDT"].reason


def test_review_portfolio_rejects_buy_when_notional_exceeds_cap():
    signal_events = {
        "BTCUSDT": _make_signal_event(
            "BTCUSDT", target_position=1, close_price=50_000.0, average_true_range=1_000.0
        )
    }
    close_price_histories = {
        "BTCUSDT": _make_close_price_series([50_000.0 + index * 100 for index in range(30)])
    }
    small_cap_engine_parameters = dict(ENGINE_PARAMETERS, initial_capital=1_000.0)

    decisions = risk_agent.review_portfolio(
        signal_events, [], {}, 10_000.0, 10_000.0,
        close_price_histories, small_cap_engine_parameters, RISK_LIMITS,
    )

    assert isinstance(decisions["BTCUSDT"], RejectionEvent)
    assert "超過風控上限" in decisions["BTCUSDT"].reason
