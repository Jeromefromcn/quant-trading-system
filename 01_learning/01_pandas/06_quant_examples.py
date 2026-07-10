"""
量化場景示例
收益率與風險指標 / 技術指標計算 / 信號生成
直接可用於 BTC(Bitcoin)/USDT 日線數據
"""

import pandas as pd
import numpy as np

# ── 模擬 BTC(Bitcoin) OHLCV(Open, High, Low, Close, Volume) 數據(實際使用時替換為真實數據) ────────────────────────

np.random.seed(42)
number_of_bars = 500
date_index = pd.date_range("2022-01-01", periods=number_of_bars, freq="B")
log_returns = np.random.normal(0.001, 0.025, number_of_bars)
close_prices = 35000 * np.exp(np.cumsum(log_returns))

price_dataframe = pd.DataFrame(
    {
        "open": close_prices * (1 + np.random.normal(0, 0.003, number_of_bars)),
        "high": close_prices * (1 + np.abs(np.random.normal(0, 0.008, number_of_bars))),
        "low": close_prices * (1 - np.abs(np.random.normal(0, 0.008, number_of_bars))),
        "close": close_prices,
        "volume": np.random.randint(500, 8000, number_of_bars).astype(float) * 1e6,
    },
    index=date_index,
)

print(
    f"數據: {len(price_dataframe)} 根日K, {price_dataframe.index[0].date()} 到 {price_dataframe.index[-1].date()}"
)
print(price_dataframe.tail(3).round(2))

# ════════════════════════════════════════════════════════════════
# 一, 收益率與風險指標
# ════════════════════════════════════════════════════════════════

print("\n" + "=" * 50)
print("一, 收益率與風險指標")
print("=" * 50)

# 日收益率
price_dataframe["daily_return"] = price_dataframe["close"].pct_change()

# 累積收益率(正確算法: 複利, 不是累加)
price_dataframe["cumulative_return"] = (
    1 + price_dataframe["daily_return"]
).cumprod() - 1

# 對數收益率(用於統計分析, 可加性)
price_dataframe["log_return"] = np.log(
    price_dataframe["close"] / price_dataframe["close"].shift(1)
)

# 年化夏普比率(假設無風險利率為 0, 252 個交易日)
sharpe_ratio = (
    price_dataframe["daily_return"].mean()
    / price_dataframe["daily_return"].std()
    * np.sqrt(252)
)

# 年化收益率
total_days = (price_dataframe.index[-1] - price_dataframe.index[0]).days
annual_return = (1 + price_dataframe["cumulative_return"].iloc[-1]) ** (
    365 / total_days
) - 1

# 年化波動率
annual_volatility = price_dataframe["daily_return"].std() * np.sqrt(252)

# 最大回撤
rolling_max = price_dataframe["close"].expanding().max()
price_dataframe["drawdown"] = price_dataframe["close"] / rolling_max - 1
max_drawdown = price_dataframe["drawdown"].min()

# 卡瑪比率(年化收益率 / 最大回撤絕對值)
calmar_ratio = annual_return / abs(max_drawdown)

print(f"累積收益率: {price_dataframe['cumulative_return'].iloc[-1]:.2%}")
print(f"年化收益率: {annual_return:.2%}")
print(f"年化波動率: {annual_volatility:.2%}")
print(f"夏普比率: {sharpe_ratio:.2f}")
print(f"最大回撤: {max_drawdown:.2%}")
print(f"卡瑪比率: {calmar_ratio:.2f}")

# 勝率(日收益率 > 0 的比例)
win_rate = (price_dataframe["daily_return"] > 0).mean()
print(f"日勝率: {win_rate:.2%}")

# ════════════════════════════════════════════════════════════════
# 二, 技術指標計算
# ════════════════════════════════════════════════════════════════

print("\n" + "=" * 50)
print("二, 技術指標計算")
print("=" * 50)

# ── 移動平均 MA(Moving Average) ──────────────────────────────────────────────

price_dataframe["moving_average_5_day"] = price_dataframe["close"].rolling(5).mean()
price_dataframe["moving_average_10_day"] = price_dataframe["close"].rolling(10).mean()
price_dataframe["moving_average_20_day"] = price_dataframe["close"].rolling(20).mean()
price_dataframe["moving_average_60_day"] = price_dataframe["close"].rolling(60).mean()
price_dataframe["exponential_moving_average_12_day"] = (
    price_dataframe["close"].ewm(span=12, adjust=False).mean()
)
price_dataframe["exponential_moving_average_26_day"] = (
    price_dataframe["close"].ewm(span=26, adjust=False).mean()
)

# ── 布林帶(Bollinger Bands) ──────────────────────────────────────────────

bollinger_band_period = 20
price_dataframe["bollinger_band_middle"] = (
    price_dataframe["close"].rolling(bollinger_band_period).mean()
)
price_dataframe["bollinger_band_standard_deviation"] = (
    price_dataframe["close"].rolling(bollinger_band_period).std()
)
price_dataframe["bollinger_band_upper"] = (
    price_dataframe["bollinger_band_middle"]
    + 2 * price_dataframe["bollinger_band_standard_deviation"]
)
price_dataframe["bollinger_band_lower"] = (
    price_dataframe["bollinger_band_middle"]
    - 2 * price_dataframe["bollinger_band_standard_deviation"]
)
price_dataframe["bollinger_band_width"] = (
    price_dataframe["bollinger_band_upper"] - price_dataframe["bollinger_band_lower"]
) / price_dataframe[
    "bollinger_band_middle"
]  # 帶寬(波動率代理)
price_dataframe["bollinger_band_percent_b"] = (
    price_dataframe["close"] - price_dataframe["bollinger_band_lower"]
) / (
    price_dataframe["bollinger_band_upper"] - price_dataframe["bollinger_band_lower"]
)  # %B 指標

# ── RSI(Relative Strength Index, 14 日) ────────────────────────────────────

daily_price_change = price_dataframe["close"].diff()
average_upward_move = daily_price_change.clip(lower=0).rolling(14).mean()  # 平均漲幅
average_downward_move = (
    (-daily_price_change.clip(upper=0)).rolling(14).mean()
)  # 平均跌幅(取絕對值)
price_dataframe["relative_strength_index"] = 100 - (
    100 / (1 + average_upward_move / average_downward_move)
)

# ── MACD(Moving Average Convergence Divergence) ──────────────────────────────────────────────────────────────

price_dataframe["moving_average_convergence_divergence"] = (
    price_dataframe["exponential_moving_average_12_day"]
    - price_dataframe["exponential_moving_average_26_day"]
)  # MACD(Moving Average Convergence Divergence) 線
price_dataframe["moving_average_convergence_divergence_signal"] = (
    price_dataframe["moving_average_convergence_divergence"]
    .ewm(span=9, adjust=False)
    .mean()
)  # 信號線
price_dataframe["moving_average_convergence_divergence_histogram"] = (
    price_dataframe["moving_average_convergence_divergence"]
    - price_dataframe["moving_average_convergence_divergence_signal"]
)  # 柱狀圖

# ── ATR(Average True Range, 平均真實波幅) ──────────────────────────────────

high_low_range = price_dataframe["high"] - price_dataframe["low"]
high_minus_previous_close = (
    price_dataframe["high"] - price_dataframe["close"].shift(1)
).abs()
low_minus_previous_close = (
    price_dataframe["low"] - price_dataframe["close"].shift(1)
).abs()
true_range = pd.concat(
    [high_low_range, high_minus_previous_close, low_minus_previous_close], axis=1
).max(axis=1)
price_dataframe["average_true_range_14_day"] = true_range.rolling(14).mean()

# ── 成交量指標 ────────────────────────────────────────────────────────────────

price_dataframe["volume_moving_average_20_day"] = (
    price_dataframe["volume"].rolling(20).mean()
)
price_dataframe["volume_ratio"] = (
    price_dataframe["volume"] / price_dataframe["volume_moving_average_20_day"]
)  # 成交量放大/縮小倍數

print(
    price_dataframe[
        [
            "close",
            "moving_average_20_day",
            "relative_strength_index",
            "moving_average_convergence_divergence",
            "average_true_range_14_day",
        ]
    ]
    .tail(5)
    .round(2)
)

# ════════════════════════════════════════════════════════════════
# 三, 信號生成
# ════════════════════════════════════════════════════════════════

print("\n" + "=" * 50)
print("三, 信號生成")
print("=" * 50)

# ── MA(Moving Average) 金叉死叉信號 ──────────────────────────────────────────────────────────

price_dataframe["moving_average_signal"] = 0
price_dataframe.loc[
    price_dataframe["moving_average_5_day"] > price_dataframe["moving_average_20_day"],
    "moving_average_signal",
] = 1  # 金叉區間: 做多
price_dataframe.loc[
    price_dataframe["moving_average_5_day"] < price_dataframe["moving_average_20_day"],
    "moving_average_signal",
] = -1  # 死叉區間: 做空

# 只在金叉/死叉發生當天觸發(去除持倉期間的重複信號)
price_dataframe["moving_average_trade_signal"] = (
    price_dataframe["moving_average_signal"].diff().fillna(0)
)
print(
    f"MA(Moving Average) 金叉次數: {(price_dataframe['moving_average_trade_signal'] > 0).sum()}"
)
print(
    f"MA(Moving Average) 死叉次數: {(price_dataframe['moving_average_trade_signal'] < 0).sum()}"
)

# ── RSI(Relative Strength Index) 超買超賣信號 ──────────────────────────────────────────────────────────

price_dataframe["relative_strength_index_signal"] = 0
price_dataframe.loc[
    price_dataframe["relative_strength_index"] < 30, "relative_strength_index_signal"
] = 1  # 做多: 超賣
price_dataframe.loc[
    price_dataframe["relative_strength_index"] > 70, "relative_strength_index_signal"
] = -1  # 做空: 超買

# ── 布林帶(Bollinger Bands) 突破信號 ────────────────────────────────────────────────────────────

price_dataframe["bollinger_band_signal"] = 0
price_dataframe.loc[
    price_dataframe["close"] > price_dataframe["bollinger_band_upper"],
    "bollinger_band_signal",
] = 1  # 上軌突破
price_dataframe.loc[
    price_dataframe["close"] < price_dataframe["bollinger_band_lower"],
    "bollinger_band_signal",
] = -1  # 下軌突破

# ── 組合信號(多個指標共振) ──────────────────────────────────────────────────

# 多個條件同時成立才觸發
price_dataframe["combined_long_signal"] = (
    (
        price_dataframe["moving_average_5_day"]
        > price_dataframe["moving_average_20_day"]
    )  # MA(Moving Average) 金叉
    & (
        price_dataframe["relative_strength_index"] < 60
    )  # RSI(Relative Strength Index) 未超買
    & (price_dataframe["volume_ratio"] > 1.2)  # 成交量放大
).astype(int)

price_dataframe["combined_short_signal"] = (
    (
        price_dataframe["moving_average_5_day"]
        < price_dataframe["moving_average_20_day"]
    )  # MA(Moving Average) 死叉
    & (
        price_dataframe["relative_strength_index"] > 40
    )  # RSI(Relative Strength Index) 未超賣
    & (price_dataframe["volume_ratio"] > 1.2)  # 成交量放大
).astype(int)

print(f"\n組合做多信號天數: {price_dataframe['combined_long_signal'].sum()}")
print(f"組合做空信號天數: {price_dataframe['combined_short_signal'].sum()}")

# 查看最近 10 天的信號
print("\n最近 10 天信號概覽:")
print(
    price_dataframe[
        [
            "close",
            "moving_average_5_day",
            "moving_average_20_day",
            "relative_strength_index",
            "moving_average_signal",
            "combined_long_signal",
            "combined_short_signal",
        ]
    ]
    .tail(10)
    .round(2)
)
