"""
Sharpe Ratio(夏普比率) 與 Max Drawdown(最大回撤) — 評估一個策略好壞最核心的兩個指標
Sharpe 衡量「每承擔一單位風險, 能換到多少報酬」, Max Drawdown 衡量「資金最慘會縮水多少」
這裡先用 BTC/USDT 買入並持有(Buy and Hold) 當範例策略, 之後章節再套到真正的交易策略上
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

# 每日報酬率 = 今天收盤價相對昨天收盤價的漲跌幅, 這是計算所有績效指標的基礎
daily_return_percentage = daily_kline_dataframe["close"].pct_change().dropna()

# Sharpe Ratio = 平均報酬 / 報酬的標準差(風險) , 再用 sqrt(365) 年化(加密貨幣全年無休交易)
# 直覺: 報酬一樣高的兩個策略, 波動越小(分母越小) Sharpe 越高, 代表賺得更「穩」
annualized_sharpe_ratio = (
    daily_return_percentage.mean() / daily_return_percentage.std() * np.sqrt(365)
)

# 把每日報酬率連乘還原成淨值曲線, 起始淨值設為 1, 方便看整體成長倍數
cumulative_equity_curve = (1 + daily_return_percentage).cumprod()
# 歷史至今的最高淨值(峰值) , 之後每天用現在淨值跟這個峰值比較, 才能算出「從高點跌了多少」
running_peak_equity = cumulative_equity_curve.cummax()
# Drawdown(回撤) = 現在淨值相對歷史峰值的跌幅, 永遠 <= 0, 數字越負代表虧得越深
drawdown_series = (cumulative_equity_curve - running_peak_equity) / running_peak_equity
maximum_drawdown = drawdown_series.min()

# 上圖看淨值曲線是否穩定向上成長, 下圖看回撤幅度, 兩者合在一起才能完整評估一個策略
figure, (equity_axes, drawdown_axes) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
equity_axes.plot(
    daily_kline_dataframe["open_time"].iloc[1:],
    cumulative_equity_curve,
    color="steelblue",
)
equity_axes.set_ylabel("淨值倍數")
equity_axes.set_title(
    f"BTC/USDT 買入並持有: Sharpe={annualized_sharpe_ratio:.2f}, "
    f"最大回撤={maximum_drawdown:.1%}"
)
drawdown_axes.fill_between(
    daily_kline_dataframe["open_time"].iloc[1:],
    drawdown_series,
    0,
    color="firebrick",
    alpha=0.5,
)
drawdown_axes.set_ylabel("回撤幅度")
figure.tight_layout()
plt.show()

print(f"年化 Sharpe Ratio: {annualized_sharpe_ratio:.2f}")
print(f"最大回撤(Max Drawdown): {maximum_drawdown:.1%}")
print(
    "Sharpe 只看平均報酬與波動, 不會告訴你曾經慘賠多少; 最大回撤才回答「我撐得住嗎」這個問題"
)
