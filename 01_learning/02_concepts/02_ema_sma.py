"""
EMA(Exponential Moving Average, 指數移動平均線) 與 SMA(Simple Moving Average, 簡單移動平均線)
用同一份 BTC/USDT 日線數據比較兩種均線, 理解 EMA 為什麼對近期價格更敏感
"""

import os
import pandas as pd
import matplotlib.pyplot as plt

# 讀取 01_ohlcv_basics.py 已經抓好並存到本地的 K 線數據, 不重複打 API
local_data_file_path = os.path.join(
    os.path.dirname(__file__), "data", "btc_usdt_daily.csv"
)
if not os.path.exists(local_data_file_path):
    raise FileNotFoundError(
        f"找不到 {local_data_file_path}, 請先執行 01_ohlcv_basics.py 產生本地數據"
    )
daily_kline_dataframe = pd.read_csv(local_data_file_path, parse_dates=["open_time"])

# SMA: 過去 20 天收盤價的算術平均, 每天權重相同, 對近期價格反應較慢
simple_moving_average_20_day = daily_kline_dataframe["close"].rolling(window=20).mean()
# EMA: 用指數權重加總, 越接近今天的價格權重越高, 對近期價格反應較快
# span=12 等同於約 12 天的有效平均週期, adjust=False 代表用遞迴公式逐天計算(業界慣用)
exponential_moving_average_12_day = (
    daily_kline_dataframe["close"].ewm(span=12, adjust=False).mean()
)
exponential_moving_average_26_day = (
    daily_kline_dataframe["close"].ewm(span=26, adjust=False).mean()
)

# 把三條均線疊加在收盤價上, 用視覺直接比較誰跟收盤價貼得更近
figure, price_axes = plt.subplots(figsize=(12, 6))
price_axes.plot(
    daily_kline_dataframe["open_time"],
    daily_kline_dataframe["close"],
    label="收盤價",
    color="black",
    linewidth=1,
)
price_axes.plot(
    daily_kline_dataframe["open_time"],
    simple_moving_average_20_day,
    label="SMA 20 日",
    color="orange",
)
price_axes.plot(
    daily_kline_dataframe["open_time"],
    exponential_moving_average_12_day,
    label="EMA 12 日",
    color="steelblue",
)
price_axes.plot(
    daily_kline_dataframe["open_time"],
    exponential_moving_average_26_day,
    label="EMA 26 日",
    color="seagreen",
)
price_axes.set_ylabel("價格(美元)")
price_axes.set_title("BTC/USDT 收盤價: EMA 與 SMA 比較")
price_axes.legend()
figure.tight_layout()
plt.show()

# 量化驗證 EMA 比 SMA 更敏感: 比較均線與當天收盤價的偏離程度, 偏離越小代表跟得越緊, 反應越快
recent_deviation_from_ema_12_day = (
    (daily_kline_dataframe["close"] - exponential_moving_average_12_day)
    .abs()
    .tail(30)
    .mean()
)
recent_deviation_from_sma_20_day = (
    (daily_kline_dataframe["close"] - simple_moving_average_20_day)
    .abs()
    .tail(30)
    .mean()
)
print(
    f"最近 30 天 EMA 12 日與收盤價的平均偏離: {recent_deviation_from_ema_12_day:.2f} 美元"
)
print(
    f"最近 30 天 SMA 20 日與收盤價的平均偏離: {recent_deviation_from_sma_20_day:.2f} 美元"
)
print(
    "EMA 偏離較小, 證明它跟收盤價貼得更緊, 對近期價格反應更快, 但也更容易被短期噪音干擾"
)
