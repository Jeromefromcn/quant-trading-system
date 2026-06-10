"""
常用模式速查 + 常見陷阱
遇到問題先查這裡
"""

import pandas as pd
import numpy as np
import warnings

# 測試數據
np.random.seed(1)
n = 100
df = pd.DataFrame({
 'open': 40000 + np.cumsum(np.random.randn(n) * 300),
 'close': 40000 + np.cumsum(np.random.randn(n) * 300),
 'high': 40000 + np.cumsum(np.random.randn(n) * 300) + 200,
 'low': 40000 + np.cumsum(np.random.randn(n) * 300) - 200,
 'volume': np.random.randint(1000, 5000, n).astype(float),
 'col1': np.random.randn(n),
 'col2': np.random.randn(n),
}, index=pd.date_range('2024-01-01', periods=n, freq='B'))
df.loc[df.index[10:15], 'volume'] = np.nan # 人為製造 NaN

# ════════════════════════════════════════════════════════════════
# 常用模式速查表
# ════════════════════════════════════════════════════════════════

print("=" * 50)
print("常用模式速查")
print("=" * 50)

# 昨日收盤價
df['prev_close'] = df['close'].shift(1)
print(f"昨日收盤(shift) :\n{df['prev_close'].head(3)}")

# N 日最高價
N = 5
df['high_5d'] = df['high'].rolling(N).max()
print(f"\n5 日最高價(rolling max) :\n{df['high_5d'].head(8)}")

# 欄位是否大於前一日(返回 bool Series)
df['is_up'] = df['close'] > df['close'].shift(1)
print(f"\n今日是否上漲(bool) :\n{df['is_up'].head(5)}")

# 刪除含 NaN 的行
df_clean = df.dropna()
print(f"\n刪除 NaN 前行數: {len(df)}, 後: {len(df_clean)}")

# 用前值填充 NaN(時序數據常用: 缺失值用上一個有效值代替)
df['volume_filled'] = df['volume'].ffill()
print(f"\nffill 後 NaN 數量: {df['volume_filled'].isna().sum()}")

# 按日期排序(確保時序正確)
df_sorted = df.sort_index()
print(f"\n按日期排序後 index 遞增: {df_sorted.index.is_monotonic_increasing}")

# 取某段時間
subset = df.loc['2024-01':'2024-03']
print(f"\n取 2024-01 到 2024-03: {len(subset)} 行")

# 日線轉周線(取最後一日收盤)
weekly_close = df['close'].resample('W').last()
print(f"\n日線轉周線 close:\n{weekly_close.head(4).round(2)}")

# 計算列的百分位排名(0 到 1)
df['vol_rank'] = df['volume'].rank(pct=True)
print(f"\n成交量百分位排名:\n{df['vol_rank'].head(5).round(3)}")

# 兩列元素級比較取較大值(axis=1 表示跨列比較)
df['max_col'] = df[['col1', 'col2']].max(axis=1)
print(f"\n兩列取最大值:\n{df[['col1', 'col2', 'max_col']].head(4).round(3)}")

# 條件賦值(類似三目運算: condition ? a : b)
df['size'] = np.where(df['volume'] > df['volume'].mean(), 'large', 'small')
print(f"\n成交量分類:\n{df['size'].value_counts()}")

# 查看缺失值數量
print(f"\n各列 NaN 數量:\n{df.isnull().sum()}")

# ════════════════════════════════════════════════════════════════
# 常見陷阱
# ════════════════════════════════════════════════════════════════

print("\n" + "=" * 50)
print("常見陷阱")
print("=" * 50)

# ── 陷阱 1: SettingWithCopyWarning ──────────────────────────────────────────

print("\n[陷阱 1] SettingWithCopyWarning")

# ❌ 錯誤寫法: 鏈式賦值, 原 df 可能不會被修改
# df[df['close'] > 45000]['new_col'] = 1 # 不要這樣寫

# ✓ 正確寫法: 用 .loc
df['new_col'] = 0
df.loc[df['close'] > 45000, 'new_col'] = 1
print(f"用 .loc 正確賦值, 高價天數: {(df['new_col'] == 1).sum()}")

# ── 陷阱 2: rolling 的前 N-1 行是 NaN ──────────────────────────────────────

print("\n[陷阱 2] rolling 前 N-1 行是 NaN")
ma20 = df['close'].rolling(20).mean()
print(f"rolling(20) 的前 19 行 NaN 數: {ma20.isna().sum()}")
# 回測時必須丟棄這些行, 否則信號計算有誤
df_bt = df.copy()
df_bt['ma20'] = ma20
df_bt = df_bt.dropna(subset=['ma20']) # 只丟棄 ma20 是 NaN 的行
print(f"dropna 後可用行數: {len(df_bt)}")

# ── 陷阱 3: 未來數據洩漏(Look-ahead bias) ─────────────────────────────────

print("\n[陷阱 3] 未來數據洩漏")
# ❌ shift(-1) 使用了明日的數據, 在信號計算中絕對不能用
df['next_close'] = df['close'].shift(-1) # 這是明日收盤, 只能用於分析, 不能用於生成信號

# ✓ 信號只能使用截至當日的數據
# rolling() 默認向前看(closed='right') , 不會洩漏;
# shift(正數) 是過去的數據, 安全.
print("shift(1) = 昨日 ✓(安全) ")
print("shift(-1) = 明日 ✗(洩漏, 只能用於事後分析) ")

# ── 陷阱 4: & | 而不是 and or ──────────────────────────────────────────────

print("\n[陷阱 4] 多條件用 & | 而非 and or")
# ❌ 這會拋 ValueError
# mask = (df['close'] > 40000) and (df['volume'] > 2000)

# ✓ 正確
mask = (df['close'] > 40000) & (df['volume'] > 2000)
print(f"同時滿足兩個條件的行數: {mask.sum()}")

# ── 陷阱 5: index 對齊問題 ─────────────────────────────────────────────────

print("\n[陷阱 5] 兩個 Series 相加時會按 index 對齊")
s1 = pd.Series([1, 2, 3], index=[0, 1, 2])
s2 = pd.Series([10, 20, 30], index=[1, 2, 3]) # index 錯開了
result = s1 + s2
print(f"s1 + s2(index 不對齊會產生 NaN) :\n{result}")
# 解決方法: 確保兩個 Series 的 index 一致, 或用 .values 忽略 index
result_values = pd.Series(s1.values + s2.values)
print(f"用 .values 忽略 index:\n{result_values}")

# ── 陷阱 6: inplace 操作 ───────────────────────────────────────────────────

print("\n[陷阱 6] dropna/sort_index 需要接收返回值, inplace=True 已不推薦")
# ❌ pandas 2.0 後 inplace=True 在某些方法上行為不一致
# df.sort_index(inplace=True)

# ✓ 推薦寫法
df = df.sort_index()
print("df = df.sort_index() ← 推薦寫法")
