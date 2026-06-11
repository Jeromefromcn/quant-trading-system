"""
apply — 向量化不夠時的退路
原則: 能向量化就向量化, apply 是最後手段
"""

import pandas as pd
import numpy as np
import time

# 測試數據
np.random.seed(42)
price_dataframe = pd.DataFrame(
    {
        "open": 40000 + np.cumsum(np.random.randn(1000) * 300),
        "close": 40000 + np.cumsum(np.random.randn(1000) * 300),
        "volume": np.random.randint(1000, 5000, 1000).astype(float),
    },
    index=pd.date_range("2021-01-01", periods=1000, freq="B"),
)

# ── apply 基本用法 ────────────────────────────────────────────────────────────
# axis=1: 對每一行應用函數(傳入的是一個 row Series)
# axis=0(默認) : 對每一列應用函數

print("=== apply 基本用法 ===")


def classify_candle(row):
    """判斷陽線/陰線"""
    if row["close"] > row["open"]:
        return "bullish"
    return "bearish"


price_dataframe["candle_direction_apply_method"] = price_dataframe.apply(
    classify_candle, axis=1
)
print(price_dataframe["candle_direction_apply_method"].value_counts())

# ── 向量化等效寫法(更快) ────────────────────────────────────────────────────

price_dataframe["candle_direction_vectorized_method"] = np.where(
    price_dataframe["close"] > price_dataframe["open"], "bullish", "bearish"
)

# 驗證結果一致
assert (
    price_dataframe["candle_direction_apply_method"]
    == price_dataframe["candle_direction_vectorized_method"]
).all(), "結果不一致! "
print("apply 和向量化結果完全一致 ✓")

# ── 性能對比: apply vs 向量化 ─────────────────────────────────────────────────

print("\n=== 性能對比(1000 行) ===")

# apply 版本
start_time = time.perf_counter()
for _ in range(100):
    price_dataframe.apply(classify_candle, axis=1)
apply_method_time_ms = (time.perf_counter() - start_time) / 100 * 1000

# 向量化版本
start_time = time.perf_counter()
for _ in range(100):
    np.where(price_dataframe["close"] > price_dataframe["open"], "bullish", "bearish")
vectorized_method_time_ms = (time.perf_counter() - start_time) / 100 * 1000

print(f"apply: {apply_method_time_ms:.2f} ms")
print(f"向量化: {vectorized_method_time_ms:.2f} ms")
print(
    f"向量化快了 {apply_method_time_ms / max(vectorized_method_time_ms, 0.001):.0f} 倍"
)

# ── 什麼情況下 apply 是合理的 ─────────────────────────────────────────────────

print("\n=== apply 合理使用場景 ===")


# 場景 1: 邏輯包含多個 if 分支, 向量化寫法會過於複雜
def classify_market_regime(row):
    """根據多個條件分類市場狀態"""
    daily_return_value = row["daily_return"]
    volume_ratio_value = row["volume_ratio"]
    if daily_return_value > 0.02 and volume_ratio_value > 1.5:
        return "breakout_up"
    elif daily_return_value < -0.02 and volume_ratio_value > 1.5:
        return "breakout_down"
    elif abs(daily_return_value) < 0.005:
        return "consolidation"
    else:
        return "normal"


price_dataframe["daily_return"] = price_dataframe["close"].pct_change()
price_dataframe["volume_moving_average_20_day"] = (
    price_dataframe["volume"].rolling(20).mean()
)
price_dataframe["volume_ratio"] = (
    price_dataframe["volume"] / price_dataframe["volume_moving_average_20_day"]
)
price_dataframe = price_dataframe.dropna()

price_dataframe["market_regime_apply_method"] = price_dataframe.apply(
    classify_market_regime, axis=1
)
print(price_dataframe["market_regime_apply_method"].value_counts())

# 向量化等效(用 np.select, 多個條件)
conditions = [
    (price_dataframe["daily_return"] > 0.02) & (price_dataframe["volume_ratio"] > 1.5),
    (price_dataframe["daily_return"] < -0.02) & (price_dataframe["volume_ratio"] > 1.5),
    price_dataframe["daily_return"].abs() < 0.005,
]
choices = ["breakout_up", "breakout_down", "consolidation"]
price_dataframe["market_regime_vectorized_method"] = np.select(
    conditions, choices, default="normal"
)

assert (
    price_dataframe["market_regime_apply_method"]
    == price_dataframe["market_regime_vectorized_method"]
).all()
print("兩種方式結果一致 ✓ — 向量化版本用 np.select 更清晰且更快")

# 場景 2: 對每列做複雜聚合(axis=0)
print("\n=== apply 對列做自定義聚合 ===")


def compute_statistics_summary(series):
    return pd.Series(
        {
            "mean": series.mean(),
            "std": series.std(),
            "skew": series.skew(),
            "q90": series.quantile(0.9),
        }
    )


column_statistics = price_dataframe[["daily_return", "volume_ratio"]].apply(
    compute_statistics_summary
)
print(column_statistics.round(4))

# ── map / applymap(元素級操作) ─────────────────────────────────────────────

print("\n=== Series.map(元素級映射) ===")
# map 比 apply 快, 適合簡單的值映射
signal_map = {1: "long", 0: "flat", -1: "short"}
price_dataframe["signal"] = np.sign(price_dataframe["daily_return"]).astype(int)
price_dataframe["signal_description"] = price_dataframe["signal"].map(signal_map)
print(
    price_dataframe[["daily_return", "signal", "signal_description"]].head(8).round(4)
)
