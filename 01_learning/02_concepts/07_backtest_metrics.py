"""
回測績效指標全集: 在 06_simple_backtest.py 的 EMA 雙均線策略基礎上,
算出評估一個策略好壞所需的完整指標, 不只看淨值曲線好不好看
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

local_data_file_path = os.path.join(
    os.path.dirname(__file__), "data", "btc_usdt_daily.csv"
)
if not os.path.exists(local_data_file_path):
    raise FileNotFoundError(
        f"找不到 {local_data_file_path}, 請先執行 01_ohlcv_basics.py 產生本地數據"
    )
daily_kline_dataframe = pd.read_csv(local_data_file_path, parse_dates=["open_time"])

exponential_moving_average_fast = (
    daily_kline_dataframe["close"].ewm(span=12, adjust=False).mean()
)
exponential_moving_average_slow = (
    daily_kline_dataframe["close"].ewm(span=26, adjust=False).mean()
)
target_position = (
    exponential_moving_average_fast > exponential_moving_average_slow
).astype(int)
# 用前一天收盤後決定的信號交易今天的報酬, 避免前視偏差(詳見 09_lookahead_bias.py)
executed_position = target_position.shift(1)
daily_return_percentage = daily_kline_dataframe["close"].pct_change()
strategy_daily_return_percentage = (executed_position * daily_return_percentage).fillna(
    0
)
strategy_equity_curve = (1 + strategy_daily_return_percentage).cumprod()

trade_identifier = (executed_position.diff() == 1).cumsum()
in_trade_rows = daily_kline_dataframe[executed_position == 1].copy()
in_trade_rows["trade_identifier"] = trade_identifier[executed_position == 1]
trade_summary_dataframe = in_trade_rows.groupby("trade_identifier").agg(
    entry_price=("close", "first"), exit_price=("close", "last")
)
trade_summary_dataframe["trade_return_percentage"] = (
    trade_summary_dataframe["exit_price"] / trade_summary_dataframe["entry_price"] - 1
)

# 總報酬: 從第一天到最後一天淨值漲了多少
total_return_percentage = strategy_equity_curve.iloc[-1] - 1
# CAGR(Compound Annual Growth Rate, 年化複合成長率) : 把總報酬換算成「如果用這個速度跑滿一年」的等效年化報酬
number_of_trading_days = len(strategy_daily_return_percentage)
annualized_growth_rate = (
    strategy_equity_curve.iloc[-1] ** (365 / number_of_trading_days) - 1
)
# Sharpe Ratio(夏普比率) : 平均日報酬 / 日報酬標準差, 再用 sqrt(365) 年化
annualized_sharpe_ratio = (
    strategy_daily_return_percentage.mean()
    / strategy_daily_return_percentage.std()
    * np.sqrt(365)
)
# Max Drawdown(最大回撤) : 淨值相對歷史峰值最深跌了多少
running_peak_equity = strategy_equity_curve.cummax()
maximum_drawdown = (
    (strategy_equity_curve - running_peak_equity) / running_peak_equity
).min()
# 勝率: 賺錢的交易筆數佔總交易筆數的比例
win_rate_percentage = (trade_summary_dataframe["trade_return_percentage"] > 0).mean()
# Profit Factor(盈虧比) : 所有賺錢交易的總報酬 / 所有賠錢交易的總報酬(取絕對值) , 大於 1 才代表整體賺錢
winning_trades_total_return = trade_summary_dataframe.loc[
    trade_summary_dataframe["trade_return_percentage"] > 0, "trade_return_percentage"
].sum()
losing_trades_total_return = trade_summary_dataframe.loc[
    trade_summary_dataframe["trade_return_percentage"] < 0, "trade_return_percentage"
].sum()
profit_factor = winning_trades_total_return / abs(losing_trades_total_return)

figure, equity_axes = plt.subplots(figsize=(12, 5))
equity_axes.plot(
    daily_kline_dataframe["open_time"], strategy_equity_curve, color="seagreen"
)
equity_axes.set_ylabel("策略淨值倍數")
equity_axes.set_title("EMA 雙均線策略淨值曲線")
figure.tight_layout()
plt.show()

print(f"總報酬: {total_return_percentage:.1%}")
print(f"年化複合成長率(CAGR): {annualized_growth_rate:.1%}")
print(f"年化 Sharpe Ratio: {annualized_sharpe_ratio:.2f}")
print(f"最大回撤(Max Drawdown): {maximum_drawdown:.1%}")
print(f"總交易筆數: {len(trade_summary_dataframe)}")
print(f"勝率: {win_rate_percentage:.1%}")
print(f"盈虧比(Profit Factor): {profit_factor:.2f}")
