"""
apply — 向量化不夠時的退路
原則: 能向量化就向量化, apply 是最後手段
"""

import pandas as pd
import numpy as np
import time

# 測試數據
np.random.seed(42)
df = pd.DataFrame({
 'open': 40000 + np.cumsum(np.random.randn(1000) * 300),
 'close': 40000 + np.cumsum(np.random.randn(1000) * 300),
 'volume': np.random.randint(1000, 5000, 1000).astype(float),
}, index=pd.date_range('2021-01-01', periods=1000, freq='B'))

# ── apply 基本用法 ────────────────────────────────────────────────────────────
# axis=1: 對每一行應用函數(傳入的是一個 row Series)
# axis=0(默認) : 對每一列應用函數

print("=== apply 基本用法 ===")

def classify_candle(row):
 """判斷陽線/陰線"""
 if row['close'] > row['open']:
 return 'bullish'
 return 'bearish'

df['candle_apply'] = df.apply(classify_candle, axis=1)
print(df['candle_apply'].value_counts())

# ── 向量化等效寫法(更快) ────────────────────────────────────────────────────

df['candle_vec'] = np.where(df['close'] > df['open'], 'bullish', 'bearish')

# 驗證結果一致
assert (df['candle_apply'] == df['candle_vec']).all(), "結果不一致! "
print("apply 和向量化結果完全一致 ✓")

# ── 性能對比: apply vs 向量化 ─────────────────────────────────────────────────

print("\n=== 性能對比(1000 行) ===")

# apply 版本
t0 = time.perf_counter()
for _ in range(100):
 df.apply(classify_candle, axis=1)
t_apply = (time.perf_counter() - t0) / 100 * 1000

# 向量化版本
t0 = time.perf_counter()
for _ in range(100):
 np.where(df['close'] > df['open'], 'bullish', 'bearish')
t_vec = (time.perf_counter() - t0) / 100 * 1000

print(f"apply: {t_apply:.2f} ms")
print(f"向量化: {t_vec:.2f} ms")
print(f"向量化快了 {t_apply / max(t_vec, 0.001):.0f} 倍")

# ── 什麼情況下 apply 是合理的 ─────────────────────────────────────────────────

print("\n=== apply 合理使用場景 ===")

# 場景 1: 邏輯包含多個 if 分支, 向量化寫法會過於複雜
def market_regime(row):
 """根據多個條件分類市場狀態"""
 ret = row['daily_return']
 vol = row['vol_ratio']
 if ret > 0.02 and vol > 1.5:
 return 'breakout_up'
 elif ret < -0.02 and vol > 1.5:
 return 'breakout_down'
 elif abs(ret) < 0.005:
 return 'consolidation'
 else:
 return 'normal'

df['daily_return'] = df['close'].pct_change()
df['avg_vol'] = df['volume'].rolling(20).mean()
df['vol_ratio'] = df['volume'] / df['avg_vol']
df = df.dropna()

df['regime_apply'] = df.apply(market_regime, axis=1)
print(df['regime_apply'].value_counts())

# 向量化等效(用 np.select, 多個條件)
conditions = [
 (df['daily_return'] > 0.02) & (df['vol_ratio'] > 1.5),
 (df['daily_return'] < -0.02) & (df['vol_ratio'] > 1.5),
 df['daily_return'].abs() < 0.005,
]
choices = ['breakout_up', 'breakout_down', 'consolidation']
df['regime_vec'] = np.select(conditions, choices, default='normal')

assert (df['regime_apply'] == df['regime_vec']).all()
print("兩種方式結果一致 ✓ — 向量化版本用 np.select 更清晰且更快")

# 場景 2: 對每列做複雜聚合(axis=0)
print("\n=== apply 對列做自定義聚合 ===")
def stats_summary(series):
 return pd.Series({
 'mean': series.mean(),
 'std': series.std(),
 'skew': series.skew(),
 'q90': series.quantile(0.9),
 })

col_stats = df[['daily_return', 'vol_ratio']].apply(stats_summary)
print(col_stats.round(4))

# ── map / applymap(元素級操作) ─────────────────────────────────────────────

print("\n=== Series.map(元素級映射) ===")
# map 比 apply 快, 適合簡單的值映射
signal_map = {1: 'long', 0: 'flat', -1: 'short'}
df['signal'] = np.sign(df['daily_return']).astype(int)
df['signal_str'] = df['signal'].map(signal_map)
print(df[['daily_return', 'signal', 'signal_str']].head(8).round(4))
