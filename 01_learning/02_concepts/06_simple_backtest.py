"""
第一個完整回測: EMA(Exponential Moving Average, 指數移動平均線) 雙均線交叉策略
快線(12 日) 上穿慢線(26 日) 進場做多, 快線下穿慢線出場, 全程用 BTC/USDT 日線跑一次端到端流程
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

exponential_moving_average_fast = (
    daily_kline_dataframe["close"].ewm(span=12, adjust=False).mean()
)
exponential_moving_average_slow = (
    daily_kline_dataframe["close"].ewm(span=26, adjust=False).mean()
)
# 信號: 快線在慢線之上代表多頭排列, 持有多單(1) ; 否則空手(0) , 用布林比較取代 if-else
is_fast_above_slow = exponential_moving_average_fast > exponential_moving_average_slow
target_position = is_fast_above_slow.astype(int)

# 重點: 用「今天收盤後決定的信號」去交易「明天的報酬」, 而不是用今天信號交易今天的報酬,
# 因為今天收盤前你還不知道今天的收盤價, 不能假裝自己能在當天用當天的收盤價成交(前視偏差)
executed_position = target_position.shift(1)
daily_return_percentage = daily_kline_dataframe["close"].pct_change()
strategy_daily_return_percentage = executed_position * daily_return_percentage
strategy_equity_curve = (1 + strategy_daily_return_percentage.fillna(0)).cumprod()

# 把每一段連續持倉切成一筆筆交易, 用 cumsum 在進場那一刻產生新的交易編號, 方便逐筆核對
trade_identifier = (executed_position.diff() == 1).cumsum()
in_trade_rows = daily_kline_dataframe[executed_position == 1].copy()
in_trade_rows["trade_identifier"] = trade_identifier[executed_position == 1]
trade_summary_dataframe = in_trade_rows.groupby("trade_identifier").agg(
    entry_date=("open_time", "first"),
    exit_date=("open_time", "last"),
    entry_price=("close", "first"),
    exit_price=("close", "last"),
)
trade_summary_dataframe["trade_return_percentage"] = (
    trade_summary_dataframe["exit_price"] / trade_summary_dataframe["entry_price"] - 1
)

# 上圖看價格與均線交叉, 下圖看策略淨值曲線是否真的隨著進出場累積成長
figure, (price_axes, equity_axes) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
price_axes.plot(
    daily_kline_dataframe["open_time"],
    daily_kline_dataframe["close"],
    color="black",
    label="收盤價",
)
price_axes.plot(
    daily_kline_dataframe["open_time"],
    exponential_moving_average_fast,
    color="steelblue",
    label="EMA 快線(12 日)",
)
price_axes.plot(
    daily_kline_dataframe["open_time"],
    exponential_moving_average_slow,
    color="orange",
    label="EMA 慢線(26 日)",
)
price_axes.set_ylabel("價格(美元)")
price_axes.set_title("EMA 雙均線交叉策略回測")
price_axes.legend()
equity_axes.plot(
    daily_kline_dataframe["open_time"], strategy_equity_curve, color="seagreen"
)
equity_axes.set_ylabel("策略淨值倍數")
figure.tight_layout()
images_output_directory_path = os.path.join(os.path.dirname(__file__), ".images")
os.makedirs(images_output_directory_path, exist_ok=True)
figure.savefig(os.path.join(images_output_directory_path, "06_simple_backtest.png"))
plt.show()

print(f"總交易筆數: {len(trade_summary_dataframe)}")
print(f"策略最終淨值倍數: {strategy_equity_curve.iloc[-1]:.2f}")
print("前 10 筆交易明細(用於手動核對進出場價格與報酬是否計算正確) :")
print(trade_summary_dataframe.head(10).to_string(index=False))
