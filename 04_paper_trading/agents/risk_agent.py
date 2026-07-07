"""
Risk agent — 比對策略目標倉位與交易所目前實際倉位, 決定要不要下單, 下多少
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
    potential_loss_usdt = order_quantity * atr_stop_multiplier * average_true_range
    return potential_loss_usdt <= account_equity_usdt * max_loss_per_trade_fraction


def check_daily_circuit_breaker(
    account_equity_usdt: float,
    day_start_equity_usdt: float,
    max_daily_loss_fraction: float = 0.04,
) -> bool:
    """回傳 True 代表尚未觸發每日熔斷; 當日開始淨值為 0 或負值時視為無法判斷, 保守放行不誤擋"""
    if day_start_equity_usdt <= 0:
        return True
    daily_loss_fraction = (day_start_equity_usdt - account_equity_usdt) / day_start_equity_usdt
    return daily_loss_fraction <= max_daily_loss_fraction


def check_max_concurrent_positions(
    current_position_count: int, market_type: str, max_positions_by_market: dict
) -> bool:
    """回傳 True 代表該類別(加密貨幣或美股) 尚未達最大同時持倉數上限"""
    return current_position_count < max_positions_by_market[market_type]


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
    candidate_returns = candidate_close_price_series.pct_change().dropna()
    for existing_returns_series in existing_position_close_price_series.values():
        existing_returns = existing_returns_series.pct_change().dropna()
        overlapping_length = min(len(candidate_returns), len(existing_returns))
        if overlapping_length < 2:
            return False
        aligned_candidate_returns = candidate_returns.iloc[-overlapping_length:].reset_index(
            drop=True
        )
        aligned_existing_returns = existing_returns.iloc[-overlapping_length:].reset_index(
            drop=True
        )
        with np.errstate(invalid="ignore", divide="ignore"):
            correlation = aligned_candidate_returns.corr(aligned_existing_returns)
        if pd.isna(correlation) or correlation > max_correlation:
            return False
    return True


def check_data_staleness(
    last_candle_open_time: datetime,
    current_time: datetime,
    bar_interval: timedelta = timedelta(days=1),
    staleness_multiplier: float = 1.5,
) -> bool:
    """
    回傳 True 代表數據新鮮, 可以繼續產生信號; False 代表已過期, 應暫停該標的的信號生成
    以「最後一根 K 線的約略收盤時間(開盤時間 + 一個週期) 」到現在經過的時間,
    對比 K 線週期的 staleness_multiplier 倍門檻 — 用相對於週期的門檻, 而非固定分鐘數,
    因為 exp_002 策略以日線決策, 固定的短分鐘數門檻對日線沒有意義(見設計文件)
    """
    approximate_close_time = last_candle_open_time + bar_interval
    time_since_close = current_time - approximate_close_time
    return time_since_close <= bar_interval * staleness_multiplier


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
