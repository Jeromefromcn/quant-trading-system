"""
OHLCV(Open 開盤價, High 最高價, Low 最低價, Close 收盤價, Volume 成交量) 基礎
從 Binance 公開行情 API(Application Programming Interface, 應用程式介面) 抓取
真實 BTC/USDT 日線, 理解一根 K 線到底在描述什麼
"""

import os
import requests
import pandas as pd
import matplotlib.pyplot as plt

# Binance 公開行情端點不需要 API Key, 任何人都能查到所有人都看得到的歷史成交價格
binance_klines_endpoint = "https://api.binance.com/api/v3/klines"
# 抓最近 180 天日線, 足夠看到一段完整的漲跌週期, 不會只看到單邊行情
request_parameters = {"symbol": "BTCUSDT", "interval": "1d", "limit": 180}
raw_klines_response = requests.get(
    binance_klines_endpoint, params=request_parameters, timeout=10
).json()

# Binance 回傳的每根 K 線是沒有欄位名的陣列, 按官方文件順序對應成有意義的欄位名
kline_columns = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trade_count", "taker_buy_base_volume",
    "taker_buy_quote_volume", "ignore",
]
daily_kline_dataframe = pd.DataFrame(raw_klines_response, columns=kline_columns)
# open_time 原始是毫秒時間戳, 轉成日期才能看懂這根 K 線發生在哪一天
daily_kline_dataframe["open_time"] = pd.to_datetime(
    daily_kline_dataframe["open_time"], unit="ms"
)
# 價格和成交量原始是字串, 轉成數字才能參與後續計算(例如算均線, 算漲跌幅)
price_and_volume_columns = ["open", "high", "low", "close", "volume"]
daily_kline_dataframe[price_and_volume_columns] = daily_kline_dataframe[
    price_and_volume_columns
].astype(float)

# 只留業務上會用到的核心欄位, 丟掉幣安內部記帳用的輔助欄位(成交額, 主動買入量等)
ohlcv_dataframe = daily_kline_dataframe[
    ["open_time", "open", "high", "low", "close", "volume"]
]
# 存成本地 CSV(Comma-Separated Values, 逗號分隔值檔案), 之後算均線, 波動率,
# 回測都直接讀這份數據, 不必每次重打 API
local_data_directory = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(local_data_directory, exist_ok=True)
ohlcv_dataframe.to_csv(
    os.path.join(local_data_directory, "btc_usdt_daily.csv"), index=False
)

# 用兩個子圖呈現一根 K 線真正在說的兩件事: 市場認可的價格, 和有多少人在交易
figure, (price_axes, volume_axes) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
# 收盤價走勢線: 代表每天市場最終認可的價格, 是最常被引用的「那個價格」
price_axes.plot(ohlcv_dataframe["open_time"], ohlcv_dataframe["close"], color="steelblue")
price_axes.set_ylabel("收盤價(美元)")
price_axes.set_title("BTC/USDT 日線收盤價與成交量(近 180 天)")
# 成交量柱狀圖: 代表當天交易的活躍程度, 量越大代表越多人認同這個價格區間
volume_axes.bar(ohlcv_dataframe["open_time"], ohlcv_dataframe["volume"], color="lightgray")
volume_axes.set_ylabel("成交量(BTC)")
figure.tight_layout()
plt.show()
print(f"已抓取 {len(ohlcv_dataframe)} 天 BTC/USDT 日線數據, 並存到本地 CSV")
