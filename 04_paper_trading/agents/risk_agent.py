"""
Risk agent — 比對策略目標倉位與交易所目前實際倉位, 決定要不要下單, 下多少
本切片(Slice 1) 只做最小風控: 買進方向的名目金額(notional) 上限檢查;
完整風控規則(每日熔斷, 相關性限制, 最大同時持倉數等) 留給後續切片, 見設計文件排除範圍
"""
import os
import sys

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


def review(
    signal_event: SignalEvent,
    current_base_asset_balance: float,
    account_equity_usdt: float,
    engine_parameters: dict,
) -> OrderEvent | RejectionEvent | None:
    """
    三種結果(不是兩種) :
    - 目標倉位與當前倉位相同 → None(無需動作)
    - 不同且在風控上限內 → OrderEvent
    - 不同但超過風控上限 → RejectionEvent(只可能發生在買進方向, 賣出方向天然受限於實際持倉)
    """
    current_position = determine_current_position(
        current_base_asset_balance, signal_event.latest_close_price
    )
    if signal_event.target_position == current_position:
        return None

    if signal_event.target_position == 0:
        # 多單 → 空手: 全部平倉, 不重新跑風險計算(compute_buy_quantity 是進場用的風險換算, 不適用平倉)
        return OrderEvent(
            symbol=signal_event.symbol, side="SELL", quantity=current_base_asset_balance
        )

    # 空手 → 多單: 用固定風險公式反推買進數量
    buy_quantity = compute_buy_quantity(
        account_equity_usdt,
        signal_event.latest_close_price,
        signal_event.latest_average_true_range,
        engine_parameters["risk_per_trade_percentage"],
        engine_parameters["atr_stop_multiplier"],
        engine_parameters["max_position_fraction"],
    )
    notional_value_usdt = buy_quantity * signal_event.latest_close_price
    maximum_allowed_notional_usdt = (
        engine_parameters["initial_capital"] * engine_parameters["max_position_fraction"]
    )
    if notional_value_usdt > maximum_allowed_notional_usdt:
        return RejectionEvent(
            symbol=signal_event.symbol,
            reason=(
                f"買進名目金額 {notional_value_usdt:.2f} USDT 超過風控上限 "
                f"{maximum_allowed_notional_usdt:.2f} USDT"
            ),
        )
    return OrderEvent(symbol=signal_event.symbol, side="BUY", quantity=buy_quantity)
