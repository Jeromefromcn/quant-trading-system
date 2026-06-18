"""
ATR(Average True Range, 平均真實波幅) — 衡量市場每天實際波動了多少
是設定止損距離最常用的波動率指標, 比固定百分比止損更能適應不同幣種與不同行情
"""

import os
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

# True Range(真實波幅) 取三者最大值: 當天高低差, 當天最高與前一天收盤的差, 當天最低與前一天收盤的差
# 之所以要納入前一天收盤, 是因為跳空(gap) 也是真實的波動, 只看當天高低差會低估隔夜跳空的風險
previous_day_close = daily_kline_dataframe["close"].shift(1)
high_minus_low = daily_kline_dataframe["high"] - daily_kline_dataframe["low"]
high_minus_previous_close = (daily_kline_dataframe["high"] - previous_day_close).abs()
low_minus_previous_close = (daily_kline_dataframe["low"] - previous_day_close).abs()
true_range = pd.concat(
    [high_minus_low, high_minus_previous_close, low_minus_previous_close], axis=1
).max(axis=1)

# ATR 是 True Range 的 14 日威爾德平滑(Wilder Smoothing) , 等同於 alpha=1/14 的指數移動平均
# 比簡單算術平均更貼近業界標準算法(J. Welles Wilder 在 1978 年提出 ATR 時的原始定義)
average_true_range_14_day = true_range.ewm(alpha=1 / 14, adjust=False).mean()

# 上圖看收盤價走勢, 下圖看 ATR 走勢, 方便對照「行情劇烈波動的時候, ATR 是否真的同步升高」
figure, (price_axes, atr_axes) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
price_axes.plot(
    daily_kline_dataframe["open_time"], daily_kline_dataframe["close"], color="black"
)
price_axes.set_ylabel("收盤價(美元)")
price_axes.set_title("BTC/USDT 收盤價與 14 日 ATR(平均真實波幅)")
atr_axes.plot(
    daily_kline_dataframe["open_time"], average_true_range_14_day, color="firebrick"
)
atr_axes.set_ylabel("ATR(美元)")
figure.tight_layout()
plt.show()

# 驗證 ATR 確實能反映波動程度: 把每天漲跌幅的標準差(常見的波動率定義) 跟 ATR 走勢的相關係數算出來
daily_return_percentage = daily_kline_dataframe["close"].pct_change()
rolling_volatility_14_day = daily_return_percentage.rolling(window=14).std()
correlation_between_atr_and_volatility = average_true_range_14_day.corr(
    rolling_volatility_14_day
)
print(
    f"ATR 與 14 日漲跌幅標準差的相關係數: {correlation_between_atr_and_volatility:.2f}"
)
print("相關係數越接近 1, 代表 ATR 越能正確捕捉到市場波動程度的變化")
