"""
績效指標庫: 把一條淨值曲線與逐筆交易換算成一組標準化的策略評估指標
與 01_learning/07_backtest_metrics.py 的算法一致, 集中在此供回測引擎與報告層引用
所有指標都以樣本外(out-of-sample) 數字才算數為前提設計, 供 STRATEGY_LOG 記錄比較
"""

import numpy as np
import pandas as pd

# 年化係數: 加密貨幣全年無休交易用 365, 美股一年約 252 個交易日
TRADING_DAYS_PER_YEAR_CRYPTO = 365
TRADING_DAYS_PER_YEAR_STOCK = 252


def maximum_drawdown(equity_curve: pd.Series) -> float:
    """
    Max Drawdown(最大回撤): 淨值相對歷史峰值最深跌了多少, 永遠 <= 0, 回答我最慘會虧多少
    """
    running_peak_equity = equity_curve.cummax()
    drawdown_series = (equity_curve - running_peak_equity) / running_peak_equity
    return float(drawdown_series.min())


def annualized_sharpe_ratio(
    daily_return_percentage: pd.Series,
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR_CRYPTO,
) -> float:
    """
    Sharpe Ratio(夏普比率): 平均日報酬 / 日報酬標準差, 再用 sqrt(交易日數) 年化
    衡量每承擔一單位波動能換到多少報酬; 報酬全程為零波動時無定義, 回傳 0 表示無風險溢酬
    """
    return_standard_deviation = daily_return_percentage.std()
    if return_standard_deviation == 0 or np.isnan(return_standard_deviation):
        return 0.0
    return float(
        daily_return_percentage.mean()
        / return_standard_deviation
        * np.sqrt(trading_days_per_year)
    )


def compound_annual_growth_rate(
    equity_curve: pd.Series,
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR_CRYPTO,
) -> float:
    """
    CAGR(Compound Annual Growth Rate, 年化複合成長率): 把總報酬換算成等效的年化報酬率
    """
    number_of_trading_days = len(equity_curve)
    if number_of_trading_days == 0:
        return 0.0
    total_growth_multiple = equity_curve.iloc[-1] / equity_curve.iloc[0]
    return float(
        total_growth_multiple ** (trading_days_per_year / number_of_trading_days) - 1
    )


def win_rate(trade_return_percentage: pd.Series) -> float:
    """勝率: 賺錢的交易筆數佔總交易筆數的比例, 無交易時回傳 0"""
    if len(trade_return_percentage) == 0:
        return 0.0
    return float((trade_return_percentage > 0).mean())


def profit_factor(trade_return_percentage: pd.Series) -> float:
    """
    Profit Factor(盈虧比): 所有賺錢交易的總報酬 / 所有賠錢交易的總報酬絕對值, 大於 1 才代表整體賺錢
    沒有任何賠錢交易時分母為零, 回傳無限大表示尚無虧損可供衡量
    """
    winning_trades_total = trade_return_percentage[trade_return_percentage > 0].sum()
    losing_trades_total = trade_return_percentage[trade_return_percentage < 0].sum()
    if losing_trades_total == 0:
        return float("inf") if winning_trades_total > 0 else 0.0
    return float(winning_trades_total / abs(losing_trades_total))


def compute_performance_metrics(
    equity_curve: pd.Series,
    daily_return_percentage: pd.Series,
    trade_return_percentage: pd.Series,
    trading_days_per_year: int = TRADING_DAYS_PER_YEAR_CRYPTO,
) -> dict:
    """
    彙總一組完整績效指標成字典, 供 report 層輸出 JSON 與 STRATEGY_LOG 記錄
    參數 equity_curve: 淨值曲線(起始值任意, 內部只看相對變化)
    參數 daily_return_percentage: 策略每日淨報酬率(已扣手續費與滑點)
    參數 trade_return_percentage: 逐筆交易的報酬率, 供勝率與盈虧比計算
    """
    return {
        "total_return": float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1),
        "compound_annual_growth_rate": compound_annual_growth_rate(
            equity_curve, trading_days_per_year
        ),
        "annualized_sharpe_ratio": annualized_sharpe_ratio(
            daily_return_percentage, trading_days_per_year
        ),
        "maximum_drawdown": maximum_drawdown(equity_curve),
        "number_of_trades": int(len(trade_return_percentage)),
        "win_rate": win_rate(trade_return_percentage),
        "profit_factor": profit_factor(trade_return_percentage),
    }
