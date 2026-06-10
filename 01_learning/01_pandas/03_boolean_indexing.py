"""
篩選與布林索引
用條件表達式篩選行 — pandas 的 if-else 替代方案
"""

import pandas as pd
import numpy as np

# 測試數據
df = pd.DataFrame(
    {
        "close": [40000, 41200, 39800, 42000, 43500, 41000, 44200, 45000, 43800, 46000],
        "volume": [1500, 2200, 1800, 3100, 2400, 1200, 3500, 4100, 2800, 3900],
        "ma5": [None, None, None, None, 41300, 41500, 42140, 43140, 43500, 44000],
        "ma20": [None] * 10,  # 數據太少, 僅示意
    },
    index=pd.date_range("2024-01-01", periods=10, freq="D"),
)
df["ma5"] = df["close"].rolling(5).mean()
df["daily_return"] = df["close"].pct_change()

# ── 基本布林索引 ─────────────────────────────────────────────────────────────
# 語義: df[條件] 返回滿足條件的行子集

print("=== 基本篩選 ===")
# 篩選收盤價 > 43000
high_days = df[df["close"] > 43000]
print(f"收盤 > 43000 的天數:\n{high_days['close']}")

# 篩選成交量高於均值的天數
avg_vol = df["volume"].mean()
high_vol = df[df["volume"] > avg_vol]
print(f"\n成交量 > 均值({avg_vol:.0f}) 的天數:\n{high_vol['volume']}")

# ── 多條件篩選 ───────────────────────────────────────────────────────────────
# 重要: 用 & (AND) 和 | (OR), 不能用 Python 的 and / or
# 每個條件必須加括號

print("\n=== 多條件篩選 ===")
# 收盤 > 43000 且成交量 > 2500(放量上漲)
strong_up = df[(df["close"] > 43000) & (df["volume"] > 2500)]
print(f"收盤>43000 且成交量>2500:\n{strong_up[['close', 'volume']]}")

# 收盤 < 41000 或成交量 < 1500(弱勢或縮量)
weak = df[(df["close"] < 41000) | (df["volume"] < 1500)]
print(f"\n收盤<41000 或成交量<1500:\n{weak[['close', 'volume']]}")

# ── .loc 條件篩選(推薦寫法) ────────────────────────────────────────────────
# .loc[行條件, 列名] 同時篩選行和列, 避免 SettingWithCopyWarning

print("\n=== .loc 篩選 ===")
# 取出高價日的 close 和 volume 兩列
result = df.loc[df["close"] > 43000, ["close", "volume"]]
print(result)

# 用 .loc 賦值(這是正確寫法, 避免鏈式賦值警告)
df["signal"] = 0
df.loc[df["close"] > df["close"].shift(1), "signal"] = 1  # 今日 > 昨日 → 上漲
df.loc[df["close"] < df["close"].shift(1), "signal"] = -1  # 今日 < 昨日 → 下跌
print(f"\n漲跌信號:\n{df['signal']}")

# ── .iloc 位置索引 ───────────────────────────────────────────────────────────
# .iloc 用數字位置, 類似 Go 的切片

print("\n=== .iloc 位置索引 ===")
print(f"最後 3 行:\n{df.iloc[-3:, :][['close', 'volume']]}")
print(f"\n第 2 到第 5 行(不含第 5) :\n{df.iloc[1:5][['close']]}")

# ── isin / between / str.contains ────────────────────────────────────────────

print("\n=== isin 篩選 ===")
target_dates = ["2024-01-03", "2024-01-07", "2024-01-09"]
subset = df[df.index.isin(pd.to_datetime(target_dates))]
print(subset[["close", "volume"]])

# between: 範圍篩選(等效於 >= A and <= B)
print("\n=== between 篩選 ===")
mid_price = df[df["close"].between(41000, 43500)]
print(f"收盤在 41000~43500 之間:\n{mid_price['close']}")

# ── np.where: 條件賦值(類似三目運算 condition ? a : b) ─────────────────────
print("\n=== np.where 條件賦值 ===")
df["candle"] = np.where(df["close"] > df["close"].shift(1), "up", "down")
print(df["candle"])

# ── 常見陷阱: SettingWithCopyWarning ─────────────────────────────────────────
print("\n=== 避免 SettingWithCopyWarning ===")

# ❌ 錯誤寫法(鏈式賦值, 可能不修改原 df)
# df[df['close'] > 43000]['new_col'] = 1 # 不要這樣寫

# ✓ 正確寫法: 用 .loc
df.loc[df["close"] > 43000, "is_high"] = True
df["is_high"] = df["is_high"].fillna(False)
print(df["is_high"])
