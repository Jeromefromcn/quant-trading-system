"""
Pandas 數據結構基礎
對應 Go 類比：Series ≈ []float64+索引，DataFrame ≈ []map[string]float64
"""

import pandas as pd
import numpy as np

# ── Series：一維帶標籤數組 ──────────────────────────────────────────────────

# 建立 Series（類似 Go 的 []float64，但每個值有標籤）
prices = pd.Series([100.0, 102.5, 98.3, 105.0, 103.2],
                   index=pd.date_range('2024-01-01', periods=5, freq='D'),
                   name='close')

print("=== Series ===")
print(prices)
print(f"\n型別: {prices.dtype}")       # float64
print(f"索引: {prices.index}")
print(f"長度: {len(prices)}")

# 取值
print(f"\n第一個值: {prices.iloc[0]}")              # 位置索引
print(f"指定日期: {prices.loc['2024-01-03']}")     # 標籤索引

# ── DataFrame：二維表格（OHLCV 就是這個） ──────────────────────────────────

data = {
    'open':   [100.0, 102.0, 98.0, 104.0, 102.0],
    'high':   [103.0, 105.0, 101.0, 107.0, 106.0],
    'low':    [99.0,  101.0, 97.0,  103.0, 101.5],
    'close':  [102.5, 98.3,  105.0, 103.2, 104.8],
    'volume': [1500,  2200,  1800,  3100,  2400],
}
df = pd.DataFrame(data, index=pd.date_range('2024-01-01', periods=5, freq='D'))

print("\n=== DataFrame ===")
print(df)
print(f"\n欄位名稱: {df.columns.tolist()}")
print(f"各列型別:\n{df.dtypes}")
print(f"shape: {df.shape}")     # (rows, cols)

# ── 基本操作 ────────────────────────────────────────────────────────────────

# 取一列（返回 Series）
close = df['close']
print(f"\n取 close 列（Series）:\n{close}")

# 取多列（返回 DataFrame）
ohlc = df[['open', 'high', 'low', 'close']]
print(f"\n取 OHLC 四列:\n{ohlc}")

# 新增計算列（向量化，不用 for loop）
df['range'] = df['high'] - df['low']          # 振幅
df['mid'] = (df['high'] + df['low']) / 2     # 中間價
print(f"\n加入 range 和 mid 列:\n{df[['high', 'low', 'range', 'mid']]}")

# ── 索引操作 ─────────────────────────────────────────────────────────────────

# .loc 用標籤（日期字符串也可以）
print(f"\n.loc 取 1/2 到 1/4:\n{df.loc['2024-01-02':'2024-01-04', 'close']}")

# .iloc 用數字位置（類似 Go 的切片 arr[1:4]）
print(f"\n.iloc 取最後 2 行:\n{df.iloc[-2:, :]}")

# ── 基本統計 ─────────────────────────────────────────────────────────────────

print(f"\nclose 描述統計:\n{df['close'].describe()}")
print(f"\n最大值: {df['close'].max()}")
print(f"最小值: {df['close'].min()}")
print(f"均值:   {df['close'].mean():.2f}")
print(f"標準差: {df['close'].std():.2f}")
