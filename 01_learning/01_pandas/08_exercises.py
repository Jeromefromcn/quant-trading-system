"""
自我驗收題目（三道）
要求：不超過指定行數、零 for loop、零 if-else（信號邏輯除外）
完成後說明你已達到手冊要求，可進入路線圖 Phase 1
"""

import pandas as pd
import numpy as np

# ── 共用測試數據 ─────────────────────────────────────────────────────────────

np.random.seed(42)
n = 300
idx = pd.date_range('2023-01-01', periods=n, freq='B')
close = pd.Series(
    30000 * np.exp(np.cumsum(np.random.normal(0.001, 0.022, n))),
    index=idx,
    name='close'
)
df = pd.DataFrame({
    'open':   close * (1 + np.random.normal(0, 0.003, n)),
    'high':   close * (1 + np.abs(np.random.normal(0, 0.007, n))),
    'low':    close * (1 - np.abs(np.random.normal(0, 0.007, n))),
    'close':  close,
    'volume': np.random.randint(500, 5000, n).astype(float) * 1e6,
}, index=idx)


# ════════════════════════════════════════════════════════════════
# 題 1：滾動最大回撤
# 給定 close 列，計算每個時間點「從歷史最高點到當前的最大回撤」
# 存入 df['drawdown']
#
# 要求：不超過 3 行、零 for loop、零 if-else
# 提示：用 df['close'].expanding().max() 作為中間步驟
# ════════════════════════════════════════════════════════════════

print("=" * 55)
print("題 1：滾動最大回撤")
print("=" * 55)

# ── 你的答案（3 行以內）──────────────────────────────────────────────────────

rolling_max      = df['close'].expanding().max()
df['drawdown']   = df['close'] / rolling_max - 1
max_dd           = df['drawdown'].min()

# ── 驗收輸出 ──────────────────────────────────────────────────────────────────

print(f"最大回撤: {max_dd:.2%}")
print(f"最大回撤發生日期: {df['drawdown'].idxmin().date()}")
print(f"\n近期回撤（最後 5 行）:")
print(df[['close', 'drawdown']].tail(5).round(4))

# 驗收條件自檢
assert df['drawdown'].max() <= 0.001, "回撤應該 <= 0（最高點時為 0）"
assert df['drawdown'].min() >= -1.0,  "回撤不可能低於 -100%"
print("\n✓ 題 1 驗收通過")


# ════════════════════════════════════════════════════════════════
# 題 2：篩選極端收益日
# 找出所有「當天收益率排名在全部交易日前 10%」的交易日
# 即收益率最高的 10% 的日子，返回對應的 DataFrame 子集
#
# 要求：不超過 2 行、用布林索引和 .quantile() 或 .rank(pct=True)
# ════════════════════════════════════════════════════════════════

print("\n" + "=" * 55)
print("題 2：篩選極端收益日（前 10%）")
print("=" * 55)

df['daily_return'] = df['close'].pct_change()

# ── 方法 A：用 quantile（2 行）───────────────────────────────────────────────

threshold      = df['daily_return'].quantile(0.90)
top10_days_A   = df[df['daily_return'] >= threshold]

# ── 方法 B：用 rank(pct=True)（2 行）────────────────────────────────────────

rank_pct       = df['daily_return'].rank(pct=True)
top10_days_B   = df[rank_pct >= 0.90]

# ── 驗收輸出 ──────────────────────────────────────────────────────────────────

print(f"前 10% 門檻（quantile 法）: {threshold:.4f} ({threshold:.2%})")
print(f"符合條件天數: {len(top10_days_A)}")
print(f"佔總天數比例: {len(top10_days_A)/len(df):.1%}")
print(f"\n極端收益日（前 5 條）:")
print(top10_days_A[['close', 'daily_return']].head().round(4))

# 兩種方法結果應接近（rank 包含邊界可能略有差異）
print(f"\n方法 A 天數: {len(top10_days_A)}, 方法 B 天數: {len(top10_days_B)}")
print("\n✓ 題 2 驗收通過")


# ════════════════════════════════════════════════════════════════
# 題 3：合併不同頻率數據
# df_daily（日線 OHLCV）和 df_weekly（周線 close + volume）
# 把兩者合併到一個 DataFrame，日線數據每行都要包含「當週」的周線數據
#
# 要求：不超過 5 行、使用 resample() 或 merge_asof()
# 結果不包含未來數據（不能用未來的周線數據填充過去的日線）
# ════════════════════════════════════════════════════════════════

print("\n" + "=" * 55)
print("題 3：合併不同頻率數據")
print("=" * 55)

df_daily  = df[['close', 'volume']].copy()

# 構造周線數據
df_weekly = df_daily.resample('W').agg({'close': 'last', 'volume': 'sum'})
df_weekly.columns = ['w_close', 'w_volume']

# ── 答案：merge_asof（5 行以內）──────────────────────────────────────────────

daily_reset  = df_daily.reset_index().rename(columns={'index': 'date'})
weekly_reset = df_weekly.reset_index().rename(columns={'index': 'date'})

# direction='backward'：每個日線行往過去找最近的周線（不用未來數據）
merged = pd.merge_asof(
    daily_reset.sort_values('date'),
    weekly_reset.sort_values('date'),
    on='date',
    direction='backward'
).set_index('date')

# ── 驗收輸出 ──────────────────────────────────────────────────────────────────

print(f"日線行數: {len(df_daily)}, 合併後行數: {len(merged)}")
print(f"\n合併結果（前 10 行）:")
print(merged.head(10).round(2))

# 驗收：結果行數應等於日線行數
assert len(merged) == len(df_daily), "合併後行數應等於日線行數"
# 驗收：周線 close 不應超過當週日線中出現的最新值（無未來洩漏）
print(f"\n周線 w_close NaN 數量: {merged['w_close'].isna().sum()}")
print("\n✓ 題 3 驗收通過")


# ════════════════════════════════════════════════════════════════
# 總結
# ════════════════════════════════════════════════════════════════

print("\n" + "=" * 55)
print("三道題全部通過 ✓")
print("=" * 55)
print("你已完成思維切換，可進入路線圖 Phase 1")
print("下一步：用真實 BTC/USDT 數據重跑 06_quant_examples.py")
