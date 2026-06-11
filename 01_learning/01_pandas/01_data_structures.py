"""
Pandas 數據結構基礎
對應 Go 類比: Series ≈ []float64+索引, DataFrame ≈ []map[string]float64
"""

import pandas as pd
import numpy as np

# ── Series: 一維帶標籤數組 ──────────────────────────────────────────────────

# 建立 Series(類似 Go 的 []float64, 但每個值有標籤)
prices = pd.Series(
    [100.0, 102.5, 98.3, 105.0, 103.2],
    index=pd.date_range("2024-01-01", periods=5, freq="D"),
    name="close",
)

print("=== Series ===")
print(prices)
print(f"\n型別: {prices.dtype}")  # float64
print(f"索引: {prices.index}")
print(f"長度: {len(prices)}")

# 取值
print(f"\n第一個值: {prices.iloc[0]}")  # 位置索引
print(f"指定日期: {prices.loc['2024-01-03']}")  # 標籤索引

# ── DataFrame: 二維表格(OHLCV(Open, High, Low, Close, Volume) 就是這個) ──────────────────────────────────

data = {
    "open": [100.0, 102.0, 98.0, 104.0, 102.0],
    "high": [103.0, 105.0, 101.0, 107.0, 106.0],
    "low": [99.0, 101.0, 97.0, 103.0, 101.5],
    "close": [102.5, 98.3, 105.0, 103.2, 104.8],
    "volume": [1500, 2200, 1800, 3100, 2400],
}
price_dataframe = pd.DataFrame(
    data, index=pd.date_range("2024-01-01", periods=5, freq="D")
)

print("\n=== DataFrame ===")
print(price_dataframe)
print(f"\n欄位名稱: {price_dataframe.columns.tolist()}")
print(f"各列型別:\n{price_dataframe.dtypes}")
print(f"shape: {price_dataframe.shape}")  # (rows, cols)

# ── 基本操作 ────────────────────────────────────────────────────────────────

# 取一列(返回 Series)
close = price_dataframe["close"]
print(f"\n取 close 列(Series) :\n{close}")

# 取多列(返回 DataFrame)
open_high_low_close_dataframe = price_dataframe[["open", "high", "low", "close"]]
print(f"\n取 OHLC(Open, High, Low, Close) 四列:\n{open_high_low_close_dataframe}")

# 新增計算列(向量化, 不用 for loop)
price_dataframe["daily_price_range"] = (
    price_dataframe["high"] - price_dataframe["low"]
)  # 振幅
price_dataframe["mid"] = (
    price_dataframe["high"] + price_dataframe["low"]
) / 2  # 中間價
print(
    f"\n加入 daily_price_range 和 mid 列:\n{price_dataframe[['high', 'low', 'daily_price_range', 'mid']]}"
)

# ── 索引操作 ─────────────────────────────────────────────────────────────────

# .loc 用標籤(日期字符串也可以)
print(
    f"\n.loc 取 1/2 到 1/4:\n{price_dataframe.loc['2024-01-02':'2024-01-04', 'close']}"
)

# .iloc 用數字位置(類似 Go 的切片 arr[1:4])
print(f"\n.iloc 取最後 2 行:\n{price_dataframe.iloc[-2:, :]}")

# ── 基本統計 ─────────────────────────────────────────────────────────────────

print(f"\nclose 描述統計:\n{price_dataframe['close'].describe()}")
print(f"\n最大值: {price_dataframe['close'].max()}")
print(f"最小值: {price_dataframe['close'].min()}")
print(f"均值: {price_dataframe['close'].mean():.2f}")
print(f"標準差: {price_dataframe['close'].std():.2f}")
