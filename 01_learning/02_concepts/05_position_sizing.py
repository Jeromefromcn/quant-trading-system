"""
固定風險倉位法(Fixed Risk Position Sizing): 决定這一筆到底該買多少
核心邏輯: 不管波動大小, 每筆交易萬一打到止損, 虧損金額永遠固定佔賬戶的一個百分比
止損距離用 ATR(Average True Range, 平均真實波幅) 的倍數設定, 波動大時自動縮小倉位
"""

import os
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

# 重新計算 14 日 ATR(做法與 03_atr.py 一致) , 倉位計算需要知道現在市場一天大概會動多少
previous_day_close = daily_kline_dataframe["close"].shift(1)
true_range = pd.concat(
    [
        daily_kline_dataframe["high"] - daily_kline_dataframe["low"],
        (daily_kline_dataframe["high"] - previous_day_close).abs(),
        (daily_kline_dataframe["low"] - previous_day_close).abs(),
    ],
    axis=1,
).max(axis=1)
average_true_range_14_day = true_range.ewm(alpha=1 / 14, adjust=False).mean()

# 假設帳戶規模 10,000 美元(對應 Pre-Phase 0 確認的模擬資金規模) , 每筆風險固定為帳戶的 1%
account_size_in_dollars = 10_000
risk_per_trade_percentage = 0.01
risk_amount_per_trade_in_dollars = account_size_in_dollars * risk_per_trade_percentage

# 止損距離設為 2 倍 ATR, 而不是固定的 5%: 固定百分比沒考慮到現在到底波動大不大,
# 用 ATR 倍數可以讓止損距離隨市場真實波動自動放大或縮小, 不會在低波動時止損設太鬆, 高波動時設太緊
stop_loss_distance_in_dollars = 2 * average_true_range_14_day
# 倉位大小(幣的數量) = 願意虧的金額 / 每單位資產一旦打到止損會虧多少
position_size_in_units = (
    risk_amount_per_trade_in_dollars / stop_loss_distance_in_dollars
)
position_value_in_dollars = position_size_in_units * daily_kline_dataframe["close"]

# 上圖看 ATR(波動程度) , 下圖看對應算出來的倉位大小, 驗證波動越大, 倉位應該越小這個關係
figure, (atr_axes, position_size_axes) = plt.subplots(
    2, 1, figsize=(12, 6), sharex=True
)
atr_axes.plot(
    daily_kline_dataframe["open_time"], average_true_range_14_day, color="firebrick"
)
atr_axes.set_ylabel("ATR(美元)")
atr_axes.set_title(
    "ATR 波動程度 vs 固定風險倉位大小(帳戶 $10,000, 每筆風險 1%, 止損 2×ATR)"
)
position_size_axes.plot(
    daily_kline_dataframe["open_time"], position_size_in_units, color="seagreen"
)
position_size_axes.set_ylabel("倉位大小(BTC 數量)")
figure.tight_layout()
images_output_directory_path = os.path.join(os.path.dirname(__file__), ".images")
os.makedirs(images_output_directory_path, exist_ok=True)
figure.savefig(os.path.join(images_output_directory_path, "05_position_sizing.png"))
plt.show()

latest_row_index = daily_kline_dataframe.index[-1]
print(f"最新一天 ATR: {average_true_range_14_day.iloc[latest_row_index]:.2f} 美元")
print(f"願意承擔的風險金額: {risk_amount_per_trade_in_dollars:.2f} 美元")
print(
    f"止損距離(2×ATR): {stop_loss_distance_in_dollars.iloc[latest_row_index]:.2f} 美元"
)
print(
    f"應買入的倉位大小: {position_size_in_units.iloc[latest_row_index]:.4f} BTC, "
    f"市值約 {position_value_in_dollars.iloc[latest_row_index]:.2f} 美元"
)
