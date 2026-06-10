"""
分組, 合併, 重採樣
groupby / concat / merge / resample — 多數據源整合的核心工具
"""

import pandas as pd
import numpy as np

# ── 測試數據 ─────────────────────────────────────────────────────────────────

idx_daily = pd.date_range("2024-01-01", periods=20, freq="B")  # 20 個交易日
np.random.seed(42)
df_daily = pd.DataFrame(
    {
        "close": 40000 + np.cumsum(np.random.randn(20) * 500),
        "volume": np.random.randint(1000, 5000, 20).astype(float),
    },
    index=idx_daily,
)
df_daily["daily_return"] = df_daily["close"].pct_change()
df_daily["month"] = df_daily.index.month
df_daily["week"] = df_daily.index.isocalendar().week.astype(int)

# ── groupby: 按分組聚合 ──────────────────────────────────────────────────────
# 語義: 類似 SQL 的 GROUP BY

print("=== groupby 按月聚合 ===")
monthly = df_daily.groupby("month").agg(
    avg_return=("daily_return", "mean"),
    total_volume=("volume", "sum"),
    trading_days=("close", "count"),
    month_end_close=("close", "last"),
)
print(monthly.round(4))

# 多種聚合方式
print("\n=== groupby 多聚合 ===")
stats = df_daily.groupby("week")["close"].agg(["min", "max", "mean", "std"])
print(stats.round(2))

# transform: 聚合結果廣播回原始長度(每行附上所在月份的均值)
print("\n=== groupby transform(保持原始行數) ===")
df_daily["month_avg_close"] = df_daily.groupby("month")["close"].transform("mean")
print(df_daily[["close", "month", "month_avg_close"]].round(2))

# ── pd.concat: 縱向拼接(行數增加) ─────────────────────────────────────────

print("\n=== pd.concat 縱向拼接 ===")
df_jan = df_daily[df_daily["month"] == 1].copy()
df_feb = df_daily[df_daily["month"] == 2].copy()

# 模擬兩個月的數據各自獲取後合併
combined = pd.concat([df_jan, df_feb])
print(f"Jan 行數: {len(df_jan)}, Feb 行數: {len(df_feb)}, 合併後: {len(combined)}")
print(combined[["close", "month"]].head())

# ── merge: 按欄位 JOIN 兩個數據源 ────────────────────────────────────────────
# 語義: 類似 SQL 的 JOIN, 用於合併兩個不同來源的 DataFrame

print("\n=== merge 按日期合併兩個數據源 ===")

# 模擬另一個數據源: 情緒指數(只有部分日期)
sentiment_dates = df_daily.index[[0, 2, 5, 8, 12, 15, 19]]
df_sentiment = pd.DataFrame(
    {
        "date": sentiment_dates,
        "fear_greed_index": [45, 62, 55, 70, 38, 80, 65],
    }
)

# 把日線 index 轉成欄位再 merge
df_with_date = df_daily.reset_index().rename(columns={"index": "date"})
merged = df_with_date.merge(
    df_sentiment, on="date", how="left"
)  # left join 保留所有日線
merged = merged.set_index("date")

print(merged[["close", "fear_greed_index"]].head(10))
print(f"\n沒有情緒數據的行(NaN) : {merged['fear_greed_index'].isna().sum()} 天")

# ── resample: 時間序列重採樣 ─────────────────────────────────────────────────
# 語義: 改變時間頻率, 日線 → 周線/月線; 前提是 index 必須是 DatetimeIndex

print("\n=== resample 日線轉周線 ===")
weekly = (
    df_daily["close"]
    .resample("W")
    .agg(
        open=("first"),
        high=("max"),
        low=("min"),
        close=("last"),
    )
)
# 簡化寫法(resample 對 Series)
weekly_close = df_daily["close"].resample("W").last()
weekly_volume = df_daily["volume"].resample("W").sum()
weekly_return = df_daily["daily_return"].resample("W").sum()  # 周收益率近似累加

df_weekly = pd.DataFrame(
    {
        "close": weekly_close,
        "volume": weekly_volume,
        "weekly_return": weekly_return,
    }
)
print(df_weekly.round(4))

print("\n=== resample 日線轉月線 OHLCV ===")
monthly_ohlcv = df_daily.resample("ME").agg(
    {
        "close": ["first", "max", "min", "last"],
        "volume": "sum",
    }
)
monthly_ohlcv.columns = ["open", "high", "low", "close", "volume"]
print(monthly_ohlcv.round(2))

# ── merge_asof: 時間對齊合併(處理不同頻率) ────────────────────────────────
# 語義: 對每個日線行, 往前找最近一條周線數據(不會用到未來數據)

print("\n=== merge_asof 日線 + 周線對齊合併 ===")
df_weekly_reset = df_weekly.reset_index().rename(columns={"index": "date"})
df_daily_reset = df_daily.reset_index().rename(columns={"index": "date"})

# 兩個 df 都必須按 key 排序
df_daily_reset = df_daily_reset.sort_values("date")
df_weekly_reset = df_weekly_reset.sort_values("date")

result = pd.merge_asof(
    df_daily_reset[["date", "close"]],
    df_weekly_reset[["date", "weekly_return"]].rename(
        columns={"weekly_return": "w_ret"}
    ),
    on="date",
    direction="backward",  # 只往過去找, 不用未來數據
)
result = result.set_index("date")
print(result.round(4))
