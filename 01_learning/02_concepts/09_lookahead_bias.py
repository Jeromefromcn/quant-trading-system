"""
前視偏差(Lookahead Bias) 演示: 如果用今天的信號去交易今天的報酬,
等於假裝自己在今天收盤前就已經知道今天的收盤價, 這在實盤是不可能做到的,
但很多新手寫的回測程式碼會不小心犯這個錯誤, 導致回測績效被嚴重高估
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# 設定中文字體, 避免圖表上的中文文字顯示成方框
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK TC", "WenQuanYi Zen Hei"]
plt.rcParams["axes.unicode_minus"] = False

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
daily_return_percentage = daily_kline_dataframe["close"].pct_change()

# 錯誤版本(有前視偏差): 直接用今天收盤後才能確定的信號去乘今天的報酬,
# 等於用收盤價算出信號, 又假裝能用同一天的收盤價成交, 現實中根本來不及反應
strategy_return_with_lookahead_bias = (
    target_position * daily_return_percentage
).fillna(0)

# 正確版本: 今天收盤後決定的信號, 只能拿去交易明天的報酬, shift(1) 把信號往後推一天執行
executed_position_without_lookahead = target_position.shift(1)
strategy_return_without_lookahead_bias = (
    executed_position_without_lookahead * daily_return_percentage
).fillna(0)

equity_curve_with_lookahead_bias = (1 + strategy_return_with_lookahead_bias).cumprod()
equity_curve_without_lookahead_bias = (
    1 + strategy_return_without_lookahead_bias
).cumprod()
sharpe_ratio_with_lookahead_bias = (
    strategy_return_with_lookahead_bias.mean()
    / strategy_return_with_lookahead_bias.std()
    * np.sqrt(365)
)
sharpe_ratio_without_lookahead_bias = (
    strategy_return_without_lookahead_bias.mean()
    / strategy_return_without_lookahead_bias.std()
    * np.sqrt(365)
)

# 把兩條淨值曲線疊在一起, 直接看出犯了前視偏差的版本看起來有多誘人, 但其實是假象
figure, equity_axes = plt.subplots(figsize=(12, 6))
equity_axes.plot(
    daily_kline_dataframe["open_time"],
    equity_curve_with_lookahead_bias,
    color="firebrick",
    label=f"有前視偏差(Sharpe={sharpe_ratio_with_lookahead_bias:.2f})",
)
equity_axes.plot(
    daily_kline_dataframe["open_time"],
    equity_curve_without_lookahead_bias,
    color="steelblue",
    label=f"無前視偏差(Sharpe={sharpe_ratio_without_lookahead_bias:.2f})",
)
equity_axes.set_ylabel("策略淨值倍數")
equity_axes.set_title("前視偏差對回測績效的影響: 看起來賺錢的版本其實無法實盤執行")
equity_axes.legend()
figure.tight_layout()
images_output_directory_path = os.path.join(os.path.dirname(__file__), ".images")
os.makedirs(images_output_directory_path, exist_ok=True)
figure.savefig(os.path.join(images_output_directory_path, "09_lookahead_bias.png"))
plt.show()

print(
    f"有前視偏差版本最終淨值倍數: {equity_curve_with_lookahead_bias.iloc[-1]:.2f}, "
    f"Sharpe={sharpe_ratio_with_lookahead_bias:.2f}"
)
print(
    f"無前視偏差版本最終淨值倍數: {equity_curve_without_lookahead_bias.iloc[-1]:.2f}, "
    f"Sharpe={sharpe_ratio_without_lookahead_bias:.2f}"
)
print("兩者的差距, 就是假裝知道未來憑空多賺到的部分, 實盤永遠拿不到這個差距")
