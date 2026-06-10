"""
位移與滾動操作 — 量化最常用的一組方法
shift / rolling / expanding / ewm / diff
"""

import pandas as pd
import numpy as np

# 構造測試數據(模擬 10 天的 BTC 收盤價)
close = pd.Series(
 [40000, 41200, 39800, 42000, 43500, 41000, 44200, 45000, 43800, 46000],
 index=pd.date_range('2024-01-01', periods=10, freq='D'),
 name='close'
)

# ── shift: 把整列向下位移 ────────────────────────────────────────────────────
# 語義: shift(1) = "昨天的值", shift(-1) = "明天的值"

print("=== shift ===")
df = pd.DataFrame({'close': close})
df['prev_close'] = df['close'].shift(1) # 昨日收盤(第一行為 NaN)
df['next_close'] = df['close'].shift(-1) # 明日收盤(最後一行為 NaN) ⚠ 有未來洩漏, 只用於分析不用於信號

# 用 shift 計算日收益率(比 pct_change() 更直觀地看原理)
df['return_manual'] = df['close'] / df['close'].shift(1) - 1
df['return_pct'] = df['close'].pct_change() # 等效簡寫

print(df[['close', 'prev_close', 'return_pct']].round(4))

# ── diff: 當前值 - 前 n 行的值 ───────────────────────────────────────────────
# 語義: 價格變動量, 動量

print("\n=== diff ===")
df['price_change'] = df['close'].diff(1) # 今日 - 昨日
df['momentum_3d'] = df['close'].diff(3) # 今日 - 3日前(3日動量)
print(df[['close', 'price_change', 'momentum_3d']])

# ── rolling: 固定窗口滾動聚合 ────────────────────────────────────────────────
# 語義: 每個位置, 取"前 n 行(含當前) " 做聚合
# 注意: 前 n-1 行因數據不夠, 結果為 NaN

print("\n=== rolling ===")
df['ma5'] = df['close'].rolling(5).mean() # 5日移動平均
df['ma3_std'] = df['close'].rolling(3).std() # 3日滾動標準差
df['high3d'] = df['close'].rolling(3).max() # 3日最高價
df['low3d'] = df['close'].rolling(3).min() # 3日最低價

print(df[['close', 'ma5', 'ma3_std', 'high3d', 'low3d']].round(2))
print("\n注意: rolling(5) 的前 4 行是 NaN, 因為數據不夠 5 個")

# ── expanding: 累積窗口(從第一行到當前行) ──────────────────────────────────
# 語義: "從歷史開始到現在" 的累積值, 窗口隨時間不斷擴大

print("\n=== expanding ===")
df['cum_max'] = df['close'].expanding().max() # 歷史最高價(每天更新)
df['cum_mean'] = df['close'].expanding().mean() # 累積均值
print(df[['close', 'cum_max', 'cum_mean']].round(2))

# 用 expanding 計算最大回撤(量化核心指標)
df['drawdown'] = df['close'] / df['close'].expanding().max() - 1
print(f"\n最大回撤: {df['drawdown'].min():.2%}")
print(df[['close', 'cum_max', 'drawdown']].round(4))

# ── ewm: 指數加權移動窗口 ─────────────────────────────────────────────────────
# 語義: 近期數據權重更高, 遠期數據權重指數衰減
# span=12 ≈ 等效 12 期 EMA; adjust=False 用遞推公式(更符合金融慣例)

print("\n=== ewm(EMA) ===")
df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
print(df[['close', 'ema12', 'ema26']].round(2))

# ── 組合示例: 布林帶 ─────────────────────────────────────────────────────────
print("\n=== 布林帶(rolling 組合應用) ===")
df['bb_mid'] = df['close'].rolling(5).mean()
df['bb_std'] = df['close'].rolling(5).std()
df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
print(df[['close', 'bb_mid', 'bb_upper', 'bb_lower']].round(2))
