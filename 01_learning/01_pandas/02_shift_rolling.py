"""
位移與滾動操作: 量化最常用的一組方法
shift / rolling / expanding / ewm / diff
"""

import pandas as pd
import numpy as np

# 構造測試數據(模擬 10 天的 BTC 收盤價)
close_price_series = pd.Series(
    [40000, 41200, 39800, 42000, 43500, 41000, 44200, 45000, 43800, 46000],
    index=pd.date_range("2024-01-01", periods=10, freq="D"),
    name="close",
)

# ── shift: 把整列向下位移 ────────────────────────────────────────────────────
# 語義: shift(1) = "昨天的值", shift(-1) = "明天的值"

print("=== shift ===")
price_dataframe = pd.DataFrame({"close": close_price_series})
price_dataframe["prev_close"] = price_dataframe["close"].shift(
    1
)  # 昨日收盤(第一行為 NaN)
price_dataframe["next_close"] = price_dataframe["close"].shift(
    -1
)  # 明日收盤(最後一行為 NaN) ⚠ 有未來洩漏, 只用於分析不用於信號

# 用 shift 計算日收益率(比 pct_change() 更直觀地看原理)
price_dataframe["return_manual"] = (
    price_dataframe["close"] / price_dataframe["close"].shift(1) - 1
)
price_dataframe["return_percentage"] = price_dataframe["close"].pct_change()  # 等效簡寫

print(
    price_dataframe[
        ["close", "prev_close", "next_close", "return_manual", "return_percentage"]
    ].round(4)
)

# ── diff: 當前值 - 前 n 行的值 ───────────────────────────────────────────────
# 語義: 價格變動量, 動量

print("\n=== diff ===")
price_dataframe["price_change"] = price_dataframe["close"].diff(1)  # 今日 - 昨日
price_dataframe["momentum_3_day"] = price_dataframe["close"].diff(
    3
)  # 今日 - 3日前(3日動量)
print(price_dataframe[["close", "price_change", "momentum_3_day"]])

# ── rolling: 固定窗口滾動聚合 ────────────────────────────────────────────────
# 語義: 每個位置, 取"前 n 行(含當前) " 做聚合
# 注意: 前 n-1 行因數據不夠, 結果為 NaN

print("\n=== rolling ===")
price_dataframe["moving_average_5_day"] = (
    price_dataframe["close"].rolling(5).mean()
)  # 5日移動平均
price_dataframe["rolling_3_day_standard_deviation"] = (
    price_dataframe["close"].rolling(3).std()
)  # 3日滾動標準差
price_dataframe["rolling_3_day_high"] = (
    price_dataframe["close"].rolling(3).max()
)  # 3日最高價
price_dataframe["rolling_3_day_low"] = (
    price_dataframe["close"].rolling(3).min()
)  # 3日最低價

print(
    price_dataframe[
        [
            "close",
            "moving_average_5_day",
            "rolling_3_day_standard_deviation",
            "rolling_3_day_high",
            "rolling_3_day_low",
        ]
    ].round(2)
)
print("\n注意: rolling(5) 的前 4 行是 NaN, 因為數據不夠 5 個")

# ── expanding: 累積窗口(從第一行到當前行) ──────────────────────────────────
# 語義: "從歷史開始到現在" 的累積值, 窗口隨時間不斷擴大

print("\n=== expanding ===")
price_dataframe["cumulative_maximum"] = (
    price_dataframe["close"].expanding().max()
)  # 歷史最高價(每天更新)
price_dataframe["cumulative_mean"] = (
    price_dataframe["close"].expanding().mean()
)  # 累積均值
print(price_dataframe[["close", "cumulative_maximum", "cumulative_mean"]].round(2))

# 用 expanding 計算最大回撤(量化核心指標)
price_dataframe["drawdown"] = (
    price_dataframe["close"] / price_dataframe["close"].expanding().max() - 1
)
print(f"\n最大回撤: {price_dataframe['drawdown'].min():.2%}")
print(price_dataframe[["close", "cumulative_maximum", "drawdown"]].round(4))

# ── ewm: 指數加權移動窗口 ─────────────────────────────────────────────────────
# 語義: 近期數據權重更高, 遠期數據權重指數衰減
# span=12 ≈ 等效 12 期 EMA(Exponential Moving Average); adjust=False 用遞推公式(更符合金融慣例)

print("\n=== ewm(EMA(Exponential Moving Average)) ===")
price_dataframe["exponential_moving_average_12_day"] = (
    price_dataframe["close"].ewm(span=12, adjust=False).mean()
)
price_dataframe["exponential_moving_average_26_day"] = (
    price_dataframe["close"].ewm(span=26, adjust=False).mean()
)
print(
    price_dataframe[
        [
            "close",
            "exponential_moving_average_12_day",
            "exponential_moving_average_26_day",
        ]
    ].round(2)
)

# ── 組合示例: 布林帶(Bollinger Bands) ─────────────────────────────────────────────────────────
print("\n=== 布林帶(Bollinger Bands)(rolling 組合應用) ===")
price_dataframe["bollinger_band_middle"] = price_dataframe["close"].rolling(5).mean()
price_dataframe["bollinger_band_standard_deviation"] = (
    price_dataframe["close"].rolling(5).std()
)
price_dataframe["bollinger_band_upper"] = (
    price_dataframe["bollinger_band_middle"]
    + 2 * price_dataframe["bollinger_band_standard_deviation"]
)
price_dataframe["bollinger_band_lower"] = (
    price_dataframe["bollinger_band_middle"]
    - 2 * price_dataframe["bollinger_band_standard_deviation"]
)
print(
    price_dataframe[
        [
            "close",
            "bollinger_band_middle",
            "bollinger_band_upper",
            "bollinger_band_lower",
        ]
    ].round(2)
)
