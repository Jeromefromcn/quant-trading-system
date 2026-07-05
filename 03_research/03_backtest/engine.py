"""
回測引擎 — 把一個策略的倉位信號, 在一份 OHLCV(開高低收量) 數據上跑成一條可評估的淨值曲線
對應 ROADMAP Phase 2 第一週的引擎規格:
- 手續費模擬: 預設 Binance Taker 0.1%
- 滑點模擬: 每筆交易加 0.05% 保守估算
- 固定風險倉位: 每筆風險 = 賬戶 × 1-2%, 止損距離 = 2×ATR, 據此計算倉位大小
- 樣本劃分: 前 70% 樣本內(調參) , 後 30% 樣本外(驗證)
- 前視偏差防護: 統一把策略信號 shift(1) 後才用於交易, 策略層不做位移

倉位大小以「佔賬戶淨值的比例(position fraction) 」表示, 便於向量化計算淨值曲線:
單位數 = (賬戶 × 每筆風險) / (止損倍數 × ATR) , 佔比 = 單位數 × 價格 / 賬戶 = 每筆風險 × 價格 / (止損倍數 × ATR)
佔比與賬戶規模無關, 且會被限制在 max_position_fraction 以內, 避免低波動時算出超過 100% 的槓桿倉位
"""

import os
import sys
from dataclasses import dataclass

import pandas as pd

# 目錄名以數字開頭無法當成 Python 套件, 手動把回測層, 策略層, 指標層目錄加入模組搜尋路徑
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "01_indicators"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02_strategies"))
from base import Strategy
from metrics import compute_performance_metrics
from volatility import average_true_range


@dataclass
class BacktestResult:
    """一次回測的完整結果, 同時保留過程數據(供手動核對) 與彙總指標(供報告)"""

    equity_curve: pd.Series
    daily_return_percentage: pd.Series
    trades: pd.DataFrame
    metrics: dict
    initial_capital: float


def split_in_sample_out_of_sample(
    ohlcv_dataframe: pd.DataFrame, in_sample_ratio: float = 0.7
):
    """
    按時間順序把數據切成前段樣本內與後段樣本外, 前 in_sample_ratio 比例為樣本內
    樣本內用來調參, 樣本外只用來最終驗證, 樣本外的數字才算數(見 10_train_test_split.py)
    """
    split_row_index = int(len(ohlcv_dataframe) * in_sample_ratio)
    in_sample_dataframe = ohlcv_dataframe.iloc[:split_row_index]
    out_of_sample_dataframe = ohlcv_dataframe.iloc[split_row_index:]
    return in_sample_dataframe, out_of_sample_dataframe


def compute_position_fraction(
    close_price: pd.Series,
    average_true_range_series: pd.Series,
    risk_per_trade_percentage: float,
    atr_stop_multiplier: float,
    max_position_fraction: float,
) -> pd.Series:
    """
    固定風險倉位法算出每天「若在當天進場, 應投入賬戶淨值的多少比例」
    佔比 = 每筆風險比例 × 價格 / (止損倍數 × ATR) , 波動(ATR) 越大佔比越小, 自動控制單筆風險
    上限 max_position_fraction 防止低波動時出現超過 100% 的槓桿倉位(現貨不做槓桿)
    """
    stop_loss_distance = atr_stop_multiplier * average_true_range_series
    position_fraction = risk_per_trade_percentage * close_price / stop_loss_distance
    return position_fraction.clip(upper=max_position_fraction)


class BacktestEngine:
    """事件驅動思路的向量化回測引擎, 只做多(long-only) , 以每日收盤價結算"""

    def __init__(
        self,
        initial_capital: float = 10_000.0,
        risk_per_trade_percentage: float = 0.01,
        atr_stop_multiplier: float = 2.0,
        atr_period: int = 14,
        fee_rate: float = 0.001,
        slippage_rate: float = 0.0005,
        max_position_fraction: float = 1.0,
        trading_days_per_year: int = 365,
    ) -> None:
        """
        參數 initial_capital: 起始賬戶淨值, 對應模擬資金規模
        參數 risk_per_trade_percentage: 每筆交易願意承擔的風險佔賬戶比例(ROADMAP 建議 1-2%)
        參數 atr_stop_multiplier: 止損距離的 ATR 倍數(ROADMAP 建議 2.0)
        參數 fee_rate: 單邊手續費率(Binance Taker 預設 0.1%)
        參數 slippage_rate: 單邊滑點率(保守估計 0.05%)
        參數 max_position_fraction: 單筆倉位佔賬戶淨值的上限, 現貨不做槓桿設 1.0
        參數 trading_days_per_year: 年化用的交易日數, 加密貨幣 365, 美股 252
        """
        self.initial_capital = initial_capital
        self.risk_per_trade_percentage = risk_per_trade_percentage
        self.atr_stop_multiplier = atr_stop_multiplier
        self.atr_period = atr_period
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self.max_position_fraction = max_position_fraction
        self.trading_days_per_year = trading_days_per_year

    def run(
        self, ohlcv_dataframe: pd.DataFrame, strategy: Strategy
    ) -> BacktestResult:
        """在給定數據上跑一次完整回測, 回傳淨值曲線, 逐筆交易與彙總指標"""
        ohlcv_dataframe = ohlcv_dataframe.reset_index(drop=True)
        close_price = ohlcv_dataframe["close"]

        # 1. 策略產生當天收盤後的目標倉位(1 多單 / 0 空手)
        target_position = strategy.generate_signals(ohlcv_dataframe)
        # 2. 前視偏差防護: 用前一天收盤後決定的信號交易今天的報酬, 引擎統一在此位移
        executed_position = target_position.shift(1).fillna(0)

        # 3. 固定風險倉位: 算出每天的目標倉位佔比, 並在進場當天鎖定佔比, 持有期間不隨 ATR 每日變動
        average_true_range_series = average_true_range(
            ohlcv_dataframe["high"],
            ohlcv_dataframe["low"],
            close_price,
            self.atr_period,
        )
        position_fraction = compute_position_fraction(
            close_price,
            average_true_range_series,
            self.risk_per_trade_percentage,
            self.atr_stop_multiplier,
            self.max_position_fraction,
        )
        # 進場當天(倉位由 0 轉 1) 鎖定佔比, 之後 forward fill 沿用; 空手日乘以 0 自然歸零
        is_entry_day = (executed_position == 1) & (executed_position.shift(1) != 1)
        locked_fraction_at_entry = position_fraction.where(is_entry_day).ffill()
        held_position_fraction = (locked_fraction_at_entry * executed_position).fillna(0)

        # 4. 交易成本: 倉位佔比的變動即為換手(turnover) , 進場, 出場, 加減倉都會產生成本
        # 每次換手的成本 = 換手佔比 × (手續費率 + 滑點率) , 進出各算一次自然涵蓋在 diff 的絕對值裡
        turnover = held_position_fraction.diff().abs().fillna(held_position_fraction)
        transaction_cost_percentage = turnover * (self.fee_rate + self.slippage_rate)

        # 5. 淨值曲線: 策略毛報酬 = 持倉佔比 × 當天資產報酬; 扣掉交易成本後累乘還原淨值
        daily_return_percentage = close_price.pct_change().fillna(0)
        strategy_gross_return = held_position_fraction * daily_return_percentage
        strategy_net_return = strategy_gross_return - transaction_cost_percentage
        equity_curve = (1 + strategy_net_return).cumprod() * self.initial_capital

        # 6. 逐筆交易明細, 供 ROADMAP 要求的「手動核對至少 10 筆交易」
        trades = self._build_trade_summary(
            ohlcv_dataframe,
            executed_position,
            held_position_fraction,
            strategy_net_return,
        )

        metrics = compute_performance_metrics(
            equity_curve,
            strategy_net_return,
            trades["trade_net_return_percentage"],
            self.trading_days_per_year,
        )
        return BacktestResult(
            equity_curve=equity_curve,
            daily_return_percentage=strategy_net_return,
            trades=trades,
            metrics=metrics,
            initial_capital=self.initial_capital,
        )

    def run_with_split(
        self,
        ohlcv_dataframe: pd.DataFrame,
        strategy: Strategy,
        in_sample_ratio: float = 0.7,
    ):
        """
        分別在樣本內與樣本外各跑一次回測, 回傳 (樣本內結果, 樣本外結果)
        調參只看樣本內, 樣本外數字用於最終判斷策略是否具備穩定優勢
        """
        in_sample_dataframe, out_of_sample_dataframe = split_in_sample_out_of_sample(
            ohlcv_dataframe, in_sample_ratio
        )
        in_sample_result = self.run(in_sample_dataframe, strategy)
        out_of_sample_result = self.run(out_of_sample_dataframe, strategy)
        return in_sample_result, out_of_sample_result

    def _build_trade_summary(
        self,
        ohlcv_dataframe: pd.DataFrame,
        executed_position: pd.Series,
        held_position_fraction: pd.Series,
        strategy_net_return: pd.Series,
    ) -> pd.DataFrame:
        """
        把每一段連續持倉切成一筆交易, 彙總進出場日期, 價格, 持倉佔比與淨報酬
        交易編號: 在每個進場日用 cumsum 產生新編號, 空手日不屬於任何交易
        """
        date_column = "open_time" if "open_time" in ohlcv_dataframe.columns else None
        is_entry_day = (executed_position == 1) & (executed_position.shift(1) != 1)
        trade_identifier = is_entry_day.cumsum()

        # 因信號已 shift(1) , 持倉在「進場信號當根 K 線的收盤」就已成交, 即在場首日的前一根收盤價
        # 記錄的進場價必須用這個成交價, (出場價 / 進場價 - 1) 才會與每日報酬累乘的結果一致, 供手動核對
        entry_execution_price = ohlcv_dataframe["close"].shift(1)

        in_trade_mask = executed_position == 1
        in_trade_rows = ohlcv_dataframe[in_trade_mask].copy()
        in_trade_rows["trade_identifier"] = trade_identifier[in_trade_mask]
        in_trade_rows["held_position_fraction"] = held_position_fraction[in_trade_mask]
        in_trade_rows["entry_execution_price"] = entry_execution_price[in_trade_mask]
        # 每天的淨報酬(含成本) 累加到所屬交易, 得到該筆交易考慮手續費後的真實報酬
        in_trade_rows["daily_net_return"] = strategy_net_return[in_trade_mask]
        if date_column is not None:
            in_trade_rows["entry_execution_date"] = ohlcv_dataframe[date_column].shift(1)[
                in_trade_mask
            ]

        if in_trade_rows.empty:
            return pd.DataFrame(
                columns=[
                    "entry_date",
                    "exit_date",
                    "entry_price",
                    "exit_price",
                    "holding_days",
                    "position_fraction",
                    "trade_net_return_percentage",
                ]
            )

        aggregation = {
            "entry_price": ("entry_execution_price", "first"),
            "exit_price": ("close", "last"),
            "holding_days": ("close", "size"),
            "position_fraction": ("held_position_fraction", "first"),
            # 一筆交易的淨報酬 = 持有期間每日淨報酬複利連乘後的總報酬
            "trade_net_return_percentage": (
                "daily_net_return",
                lambda daily_returns: (1 + daily_returns).prod() - 1,
            ),
        }
        if date_column is not None:
            aggregation["entry_date"] = ("entry_execution_date", "first")
            aggregation["exit_date"] = (date_column, "last")

        trade_summary = in_trade_rows.groupby("trade_identifier").agg(**aggregation)
        return trade_summary.reset_index(drop=True)
