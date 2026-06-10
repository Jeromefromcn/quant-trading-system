"""
量化場景示例
收益率與風險指標 / 技術指標計算 / 信號生成
直接可用於 BTC/USDT 日線數據
"""

import pandas as pd
import numpy as np

# ── 模擬 BTC OHLCV 數據（實際使用時替換為真實數據）────────────────────────

np.random.seed(42)
n = 500
idx = pd.date_range('2022-01-01', periods=n, freq='B')
log_returns = np.random.normal(0.001, 0.025, n)
close_prices = 35000 * np.exp(np.cumsum(log_returns))

df = pd.DataFrame({
    'open':   close_prices * (1 + np.random.normal(0, 0.003, n)),
    'high':   close_prices * (1 + np.abs(np.random.normal(0, 0.008, n))),
    'low':    close_prices * (1 - np.abs(np.random.normal(0, 0.008, n))),
    'close':  close_prices,
    'volume': np.random.randint(500, 8000, n).astype(float) * 1e6,
}, index=idx)

print(f"數據: {len(df)} 根日K，{df.index[0].date()} 到 {df.index[-1].date()}")
print(df.tail(3).round(2))

# ════════════════════════════════════════════════════════════════
# 一、收益率與風險指標
# ════════════════════════════════════════════════════════════════

print("\n" + "="*50)
print("一、收益率與風險指標")
print("="*50)

# 日收益率
df['daily_return'] = df['close'].pct_change()

# 累積收益率（正確算法：複利，不是累加）
df['cum_return'] = (1 + df['daily_return']).cumprod() - 1

# 對數收益率（用於統計分析，可加性）
df['log_return'] = np.log(df['close'] / df['close'].shift(1))

# 年化夏普比率（假設無風險利率為 0，252 個交易日）
sharpe = df['daily_return'].mean() / df['daily_return'].std() * np.sqrt(252)

# 年化收益率
total_days = (df.index[-1] - df.index[0]).days
annual_return = (1 + df['cum_return'].iloc[-1]) ** (365 / total_days) - 1

# 年化波動率
annual_vol = df['daily_return'].std() * np.sqrt(252)

# 最大回撤
rolling_max = df['close'].expanding().max()
df['drawdown'] = df['close'] / rolling_max - 1
max_drawdown = df['drawdown'].min()

# 卡瑪比率（年化收益率 / 最大回撤絕對值）
calmar = annual_return / abs(max_drawdown)

print(f"累積收益率:   {df['cum_return'].iloc[-1]:.2%}")
print(f"年化收益率:   {annual_return:.2%}")
print(f"年化波動率:   {annual_vol:.2%}")
print(f"夏普比率:     {sharpe:.2f}")
print(f"最大回撤:     {max_drawdown:.2%}")
print(f"卡瑪比率:     {calmar:.2f}")

# 勝率（日收益率 > 0 的比例）
win_rate = (df['daily_return'] > 0).mean()
print(f"日勝率:       {win_rate:.2%}")

# ════════════════════════════════════════════════════════════════
# 二、技術指標計算
# ════════════════════════════════════════════════════════════════

print("\n" + "="*50)
print("二、技術指標計算")
print("="*50)

# ── 移動平均 ──────────────────────────────────────────────────────────────

df['ma5']   = df['close'].rolling(5).mean()
df['ma10']  = df['close'].rolling(10).mean()
df['ma20']  = df['close'].rolling(20).mean()
df['ma60']  = df['close'].rolling(60).mean()
df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()

# ── 布林帶（Bollinger Bands）──────────────────────────────────────────────

period = 20
df['bb_mid']   = df['close'].rolling(period).mean()
df['bb_std']   = df['close'].rolling(period).std()
df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']  # 帶寬（波動率代理）
df['bb_pct']   = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])  # %B 指標

# ── RSI（Relative Strength Index，14 日）────────────────────────────────────

delta = df['close'].diff()
gain  = delta.clip(lower=0).rolling(14).mean()   # 平均漲幅
loss  = (-delta.clip(upper=0)).rolling(14).mean() # 平均跌幅（取絕對值）
df['rsi'] = 100 - (100 / (1 + gain / loss))

# ── MACD ─────────────────────────────────────────────────────────────────────

df['macd']        = df['ema12'] - df['ema26']                          # MACD 線
df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()        # 信號線
df['macd_hist']   = df['macd'] - df['macd_signal']                     # 柱狀圖

# ── ATR（Average True Range，平均真實波幅）──────────────────────────────────

high_low   = df['high'] - df['low']
high_close = (df['high'] - df['close'].shift(1)).abs()
low_close  = (df['low']  - df['close'].shift(1)).abs()
true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
df['atr14'] = true_range.rolling(14).mean()

# ── 成交量指標 ────────────────────────────────────────────────────────────────

df['vol_ma20']  = df['volume'].rolling(20).mean()
df['vol_ratio'] = df['volume'] / df['vol_ma20']   # 成交量放大/縮小倍數

print(df[['close', 'ma20', 'rsi', 'macd', 'atr14']].tail(5).round(2))

# ════════════════════════════════════════════════════════════════
# 三、信號生成
# ════════════════════════════════════════════════════════════════

print("\n" + "="*50)
print("三、信號生成")
print("="*50)

# ── MA 金叉死叉信號 ──────────────────────────────────────────────────────────

df['ma_signal'] = 0
df.loc[df['ma5'] > df['ma20'], 'ma_signal'] = 1   # 金叉區間：做多
df.loc[df['ma5'] < df['ma20'], 'ma_signal'] = -1  # 死叉區間：做空

# 只在金叉/死叉發生當天觸發（去除持倉期間的重複信號）
df['ma_trade'] = df['ma_signal'].diff().fillna(0)
print(f"MA 金叉次數: {(df['ma_trade'] > 0).sum()}")
print(f"MA 死叉次數: {(df['ma_trade'] < 0).sum()}")

# ── RSI 超買超賣信號 ──────────────────────────────────────────────────────────

df['rsi_signal'] = 0
df.loc[df['rsi'] < 30, 'rsi_signal'] = 1   # 超賣 → 做多
df.loc[df['rsi'] > 70, 'rsi_signal'] = -1  # 超買 → 做空

# ── 布林帶突破信號 ────────────────────────────────────────────────────────────

df['bb_signal'] = 0
df.loc[df['close'] > df['bb_upper'], 'bb_signal'] = 1   # 上軌突破
df.loc[df['close'] < df['bb_lower'], 'bb_signal'] = -1  # 下軌突破

# ── 組合信號（多個指標共振）──────────────────────────────────────────────────

# 多個條件同時成立才觸發
df['combo_long'] = (
    (df['ma5'] > df['ma20']) &     # MA 金叉
    (df['rsi'] < 60) &             # RSI 未超買
    (df['vol_ratio'] > 1.2)        # 成交量放大
).astype(int)

df['combo_short'] = (
    (df['ma5'] < df['ma20']) &     # MA 死叉
    (df['rsi'] > 40) &             # RSI 未超賣
    (df['vol_ratio'] > 1.2)        # 成交量放大
).astype(int)

print(f"\n組合做多信號天數: {df['combo_long'].sum()}")
print(f"組合做空信號天數: {df['combo_short'].sum()}")

# 查看最近 10 天的信號
print("\n最近 10 天信號概覽:")
print(df[['close', 'ma5', 'ma20', 'rsi', 'ma_signal', 'combo_long', 'combo_short']].tail(10).round(2))
