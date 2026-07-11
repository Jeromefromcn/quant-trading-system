"""
Risk agent: 比對策略目標倉位與交易所目前實際倉位, 決定要不要下單, 下多少
本切片(Slice 1) 只做最小風控: 買進方向的名目金額(notional) 上限檢查;
完整風控規則(每日熔斷, 相關性限制, 最大同時持倉數等) 留給後續切片, 見設計文件排除範圍
"""
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

_agents_directory = os.path.dirname(os.path.abspath(__file__))
_paper_trading_directory = os.path.dirname(_agents_directory)
_repository_root = os.path.dirname(_paper_trading_directory)
sys.path.insert(0, os.path.join(_repository_root, "03_research", "03_backtest"))
sys.path.insert(0, _paper_trading_directory)

from engine import compute_position_fraction  # noqa: E402

from events import OrderEvent, RejectionEvent, SignalEvent  # noqa: E402

# BTC 市值低於這個 USDT 門檻視為粉塵(dust) , 不算真的持有部位
DUST_VALUE_THRESHOLD_USDT = 10.0


def determine_current_position(
    base_asset_balance: float, base_asset_price_in_usdt: float
) -> int:
    """把交易所回傳的實際餘額換算成 0(空手) 或 1(多單) , 市值低於粉塵門檻視為空手"""
    return int(base_asset_balance * base_asset_price_in_usdt >= DUST_VALUE_THRESHOLD_USDT)


def compute_buy_quantity(
    account_equity_usdt: float,
    close_price: float,
    average_true_range: float,
    risk_per_trade_percentage: float,
    atr_stop_multiplier: float,
    max_position_fraction: float,
) -> float:
    """用引擎既有的固定風險倉位公式算出買進數量(單位: 標的資產, 例如 BTC) , 與回測時的進場邏輯一致"""
    position_fraction_series = compute_position_fraction(
        pd.Series([close_price]),
        pd.Series([average_true_range]),
        risk_per_trade_percentage,
        atr_stop_multiplier,
        max_position_fraction,
    )
    position_value_usdt = account_equity_usdt * position_fraction_series.iloc[0]
    return position_value_usdt / close_price


def compute_potential_loss_usdt(
    order_quantity: float, average_true_range: float, atr_stop_multiplier: float
) -> float:
    """算出這筆開倉若觸及停損會虧損多少 USDT(數量 x 停損距離) , 與 check_max_loss_per_trade 內部算法相同"""
    return order_quantity * atr_stop_multiplier * average_true_range


def check_max_loss_per_trade(
    order_quantity: float,
    average_true_range: float,
    atr_stop_multiplier: float,
    account_equity_usdt: float,
    max_loss_per_trade_fraction: float = 0.015,
) -> bool:
    """
    估算這筆開倉若觸及停損會虧損多少(數量 × 停損距離) , 回傳 True 代表未超過帳戶淨值上限
    這與既有的名目金額上限是不同維度的雙層防呆(defense-in-depth) : 一個限制潛在虧損,
    一個限制部位金額本身; 在凍結的 exp_002 風險比例(1%) 下, 這條規則正常情況下不會觸發,
    只在風險比例設定被改動或計算異常時才會攔下, 與既有名目金額上限的防呆精神一致
    """
    potential_loss_usdt = compute_potential_loss_usdt(
        order_quantity, average_true_range, atr_stop_multiplier
    )
    return potential_loss_usdt <= account_equity_usdt * max_loss_per_trade_fraction


def compute_daily_loss_fraction(account_equity_usdt: float, day_start_equity_usdt: float) -> float:
    """算出當日虧損比例; 當日開始淨值為 0 或負值時視為無法判斷, 回傳 0.0(保守, 不誤判為熔斷)"""
    if day_start_equity_usdt <= 0:
        return 0.0
    return (day_start_equity_usdt - account_equity_usdt) / day_start_equity_usdt


def check_daily_circuit_breaker(
    account_equity_usdt: float,
    day_start_equity_usdt: float,
    max_daily_loss_fraction: float = 0.04,
) -> bool:
    """回傳 True 代表尚未觸發每日熔斷; 當日開始淨值為 0 或負值時視為無法判斷, 保守放行不誤擋"""
    if day_start_equity_usdt <= 0:
        return True
    return compute_daily_loss_fraction(account_equity_usdt, day_start_equity_usdt) <= max_daily_loss_fraction


def check_max_concurrent_positions(
    current_position_count: int, market_type: str, max_positions_by_market: dict
) -> bool:
    """回傳 True 代表該類別(加密貨幣或美股) 尚未達最大同時持倉數上限"""
    return current_position_count < max_positions_by_market[market_type]


def compute_max_correlation_against_existing_positions(
    candidate_close_price_series: pd.Series, existing_position_close_price_series: dict
) -> float | None:
    """
    回傳候選標的與所有現有持倉中最高的日報酬率相關係數(correlation coefficient) . 無現有持倉時
    回傳 None(代表無需比較) . 任一現有持倉缺少至少 2 個重疊報酬率數據點, 或相關係數算出 NaN
    (例如某段價格完全不變) , 同樣回傳 None(代表數據不足以計算, 而非數值為 0) , 呼叫端應將 None
    視為無法確認風險, 保守處理
    """
    if not existing_position_close_price_series:
        return None
    candidate_returns = candidate_close_price_series.pct_change().dropna()
    correlations = []
    for existing_returns_series in existing_position_close_price_series.values():
        existing_returns = existing_returns_series.pct_change().dropna()
        overlapping_length = min(len(candidate_returns), len(existing_returns))
        if overlapping_length < 2:
            return None
        aligned_candidate_returns = candidate_returns.iloc[-overlapping_length:].reset_index(
            drop=True
        )
        aligned_existing_returns = existing_returns.iloc[-overlapping_length:].reset_index(
            drop=True
        )
        with np.errstate(invalid="ignore", divide="ignore"):
            correlation = aligned_candidate_returns.corr(aligned_existing_returns)
        if pd.isna(correlation):
            return None
        correlations.append(correlation)
    return max(correlations)


def check_correlation_limit(
    candidate_close_price_series: pd.Series,
    existing_position_close_price_series: dict,
    max_correlation: float = 0.8,
) -> bool:
    """
    回傳 True 代表候選標的與所有現有持倉的日報酬率相關係數皆未超過上限, 可以開倉
    任一現有持倉缺少至少 2 個重疊報酬率數據點, 或相關係數算出 NaN(例如某段價格完全不變) ,
    視為無法確認風險, 直接回傳 False(風控規則寧可保守拒絕, 不因數據不足而放行)
    """
    if not existing_position_close_price_series:
        return True
    max_correlation_value = compute_max_correlation_against_existing_positions(
        candidate_close_price_series, existing_position_close_price_series
    )
    if max_correlation_value is None:
        return False
    # pandas 的 corr() 回傳 numpy.float64, 比較結果是 numpy.bool_, 這裡轉成 Python 原生 bool
    # 以維持既有函式簽名回傳型別的一致性(既有測試用 is True / is False 做嚴格型別比對)
    return bool(max_correlation_value <= max_correlation)


def compute_staleness_detail(
    last_candle_open_time: datetime,
    current_time: datetime,
    bar_interval: timedelta = timedelta(days=1),
    staleness_multiplier: float = 1.5,
) -> dict:
    """
    回傳 {"time_since_close_seconds": 已過期秒數(可能為負, 代表尚未到約略收盤時間) ,
    "threshold_seconds": 門檻秒數}, 與 check_data_staleness 的計算邏輯相同, 供
    run_once.py 記錄過期細節用
    """
    approximate_close_time = last_candle_open_time + bar_interval
    time_since_close = current_time - approximate_close_time
    threshold = bar_interval * staleness_multiplier
    return {
        "time_since_close_seconds": time_since_close.total_seconds(),
        "threshold_seconds": threshold.total_seconds(),
    }


def check_data_staleness(
    last_candle_open_time: datetime,
    current_time: datetime,
    bar_interval: timedelta = timedelta(days=1),
    staleness_multiplier: float = 1.5,
) -> bool:
    """
    回傳 True 代表數據新鮮, 可以繼續產生信號; False 代表已過期, 應暫停該標的的信號生成
    以最後一根 K 線的約略收盤時間(開盤時間 + 一個週期) 到現在經過的時間,
    對比 K 線週期的 staleness_multiplier 倍門檻: 用相對於週期的門檻, 而非固定分鐘數,
    因為 exp_002 策略以日線決策, 固定的短分鐘數門檻對日線沒有意義(見設計文件)
    """
    detail = compute_staleness_detail(
        last_candle_open_time, current_time, bar_interval, staleness_multiplier
    )
    return detail["time_since_close_seconds"] <= detail["threshold_seconds"]


SYMBOL_MARKET_TYPES = {
    "BTCUSDT": "crypto",
    "ETHUSDT": "crypto",
    "VOO": "stocks",
    "QQQ": "stocks",
}


def review_portfolio(
    signal_events: dict,
    stale_symbols: dict,
    current_base_asset_balances: dict,
    account_equity_usdt: float,
    day_start_equity_usdt: float,
    close_price_histories: dict,
    engine_parameters: dict,
    risk_limits: dict,
) -> dict:
    """
    對整批標的一次做出風控決策(取代 Slice 1 的單標的 review) , 依序套用 :
    全域每日熔斷(一次) , 逐標的數據異常, 逐標的目標倉位比對, 開倉方向四項檢查
    (單筆最大虧損, 最大同時持倉數, 相關性限制, 名目金額上限) . 依 SYMBOL_MARKET_TYPES 的固定
    標的順序處理, 讓最大同時持倉數與相關性限制的比較基準包含本次批次已核准的開倉,
    結果因此具決定性(取決於固定順序, 不取決於呼叫端字典的建構順序) , 見設計文件行為後果說明
    """
    decisions = {}
    ordered_symbols = [symbol for symbol in SYMBOL_MARKET_TYPES if symbol in signal_events]

    circuit_breaker_ok = check_daily_circuit_breaker(
        account_equity_usdt, day_start_equity_usdt, risk_limits["max_daily_loss_fraction"]
    )
    if not circuit_breaker_ok:
        daily_loss_fraction = compute_daily_loss_fraction(account_equity_usdt, day_start_equity_usdt)
        for symbol in ordered_symbols + list(stale_symbols):
            decisions[symbol] = RejectionEvent(
                symbol=symbol,
                reason="每日虧損熔斷已觸發, 停止當日所有交易",
                computed_value=daily_loss_fraction,
                limit_value=risk_limits["max_daily_loss_fraction"],
            )
        return decisions

    for symbol in stale_symbols:
        decisions[symbol] = RejectionEvent(
            symbol=symbol,
            reason="數據已過期, 暫停信號生成",
            computed_value=stale_symbols[symbol]["time_since_close_seconds"],
            limit_value=stale_symbols[symbol]["threshold_seconds"],
        )

    open_long_symbols = [
        symbol
        for symbol in ordered_symbols
        if determine_current_position(
            current_base_asset_balances.get(symbol, 0.0),
            signal_events[symbol].latest_close_price,
        )
        == 1
    ]

    for symbol in ordered_symbols:
        signal_event = signal_events[symbol]
        current_position = determine_current_position(
            current_base_asset_balances.get(symbol, 0.0), signal_event.latest_close_price
        )
        if signal_event.target_position == current_position:
            decisions[symbol] = None
            continue

        if signal_event.target_position == 0:
            decisions[symbol] = OrderEvent(
                symbol=symbol, side="SELL", quantity=current_base_asset_balances.get(symbol, 0.0)
            )
            if symbol in open_long_symbols:
                open_long_symbols.remove(symbol)
            continue

        buy_quantity = compute_buy_quantity(
            account_equity_usdt,
            signal_event.latest_close_price,
            signal_event.latest_average_true_range,
            engine_parameters["risk_per_trade_percentage"],
            engine_parameters["atr_stop_multiplier"],
            engine_parameters["max_position_fraction"],
        )

        if not check_max_loss_per_trade(
            buy_quantity,
            signal_event.latest_average_true_range,
            engine_parameters["atr_stop_multiplier"],
            account_equity_usdt,
            risk_limits["max_loss_per_trade_fraction"],
        ):
            potential_loss_usdt = compute_potential_loss_usdt(
                buy_quantity, signal_event.latest_average_true_range, engine_parameters["atr_stop_multiplier"]
            )
            decisions[symbol] = RejectionEvent(
                symbol=symbol,
                reason="單筆潛在虧損超過風控上限",
                computed_value=potential_loss_usdt / account_equity_usdt,
                limit_value=risk_limits["max_loss_per_trade_fraction"],
            )
            continue

        market_type = SYMBOL_MARKET_TYPES[symbol]
        positions_in_same_market_count = sum(
            1
            for other_symbol in open_long_symbols
            if SYMBOL_MARKET_TYPES.get(other_symbol) == market_type
        )
        if not check_max_concurrent_positions(
            positions_in_same_market_count, market_type, risk_limits["max_positions_by_market"]
        ):
            decisions[symbol] = RejectionEvent(
                symbol=symbol,
                reason=f"已達 {market_type} 類別最大同時持倉數上限",
                computed_value=positions_in_same_market_count,
                limit_value=risk_limits["max_positions_by_market"][market_type],
            )
            continue

        existing_position_close_price_series = {
            other_symbol: close_price_histories[other_symbol]
            for other_symbol in open_long_symbols
            if other_symbol in close_price_histories
        }
        if not check_correlation_limit(
            close_price_histories[symbol],
            existing_position_close_price_series,
            risk_limits["max_correlation"],
        ):
            max_correlation_value = compute_max_correlation_against_existing_positions(
                close_price_histories[symbol], existing_position_close_price_series
            )
            if max_correlation_value is None:
                decisions[symbol] = RejectionEvent(
                    symbol=symbol,
                    reason="相關係數無法計算(數據不足或無變化), 風控保守拒絕",
                    computed_value=None,
                    limit_value=risk_limits["max_correlation"],
                )
            else:
                decisions[symbol] = RejectionEvent(
                    symbol=symbol,
                    reason="與現有持倉相關係數超過風控上限",
                    computed_value=max_correlation_value,
                    limit_value=risk_limits["max_correlation"],
                )
            continue

        notional_value_usdt = buy_quantity * signal_event.latest_close_price
        maximum_allowed_notional_usdt = (
            engine_parameters["initial_capital"] * engine_parameters["max_position_fraction"]
        )
        if notional_value_usdt > maximum_allowed_notional_usdt:
            decisions[symbol] = RejectionEvent(
                symbol=symbol,
                reason=(
                    f"買進名目金額 {notional_value_usdt:.2f} USDT 超過風控上限 "
                    f"{maximum_allowed_notional_usdt:.2f} USDT"
                ),
                computed_value=notional_value_usdt,
                limit_value=maximum_allowed_notional_usdt,
            )
            continue

        limit_price = signal_event.latest_close_price if market_type == "stocks" else None
        decisions[symbol] = OrderEvent(
            symbol=symbol, side="BUY", quantity=buy_quantity, limit_price=limit_price
        )
        open_long_symbols.append(symbol)

    return decisions
