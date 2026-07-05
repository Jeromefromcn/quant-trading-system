"""
數據源外部錨定(validation) — 用一個獨立的第二數據源交叉驗證本地快取的正確性
回測引擎的不變量測試(tests/test_engine_invariants.py) 只能證明「引擎與輸入數據一致」(verification) ,
無法證明「輸入數據本身符合真實市場」. 若抓取器把欄位對錯, 所有不變量照樣全綠, 數字卻系統性錯誤.
本腳本把 Binance 快取的 BTC 日線, 拿去和完全獨立的 Kraken 交易所日線逐日比對收盤價, 提供那一個外部錨.

這是「每個數據源做一次」的驗證, 不是每次跑都要做, 也不放進 pytest(需要網路且依賴外部服務) .
Binance 報價為 BTC/USDT, Kraken 為 BTC/USD, 兩者非同一標的, 收盤價會有微小價差, 故用容差判定而非精確相等.
"""

import datetime
import os

import pandas as pd
import requests

KRAKEN_OHLC_ENDPOINT = "https://api.kraken.com/0/public/OHLC"
# 交叉驗證容差: 不同交易所 + USD 對 USDT 的正常價差, 經驗上日線收盤差異在 1% 以內
CROSS_SOURCE_TOLERANCE = 0.01
# 若任一天價差超過此上限, 視為可疑, 需人工調查(可能是抓取器欄位對錯或數據源異常)
SUSPICIOUS_DIFFERENCE_THRESHOLD = 0.02


def fetch_kraken_daily_close(kraken_pair: str = "XBTUSD") -> pd.Series:
    """從 Kraken 公開 API 抓每日收盤價, 回傳以日期為索引的 Series; Kraken 公開端點不需認證"""
    response = requests.get(
        KRAKEN_OHLC_ENDPOINT,
        params={"pair": kraken_pair, "interval": 1440},
        timeout=30,
    )
    response.raise_for_status()
    response_body = response.json()
    if response_body.get("error"):
        raise RuntimeError(f"Kraken API 回傳錯誤: {response_body['error']}")

    # result 內含一個以 Kraken 內部代號為名的欄位(例如 XXBTZUSD) 與一個 last 欄位, 取前者
    result_payload = response_body["result"]
    pair_key = next(key for key in result_payload if key != "last")
    ohlc_rows = result_payload[pair_key]

    kraken_dataframe = pd.DataFrame(
        ohlc_rows,
        columns=[
            "time",
            "open",
            "high",
            "low",
            "close",
            "vwap",
            "volume",
            "count",
        ],
    )
    kraken_dataframe["date"] = pd.to_datetime(
        kraken_dataframe["time"], unit="s"
    ).dt.normalize()
    kraken_dataframe["close"] = kraken_dataframe["close"].astype(float)
    return kraken_dataframe.set_index("date")["close"]


def validate_binance_cache_against_kraken(cache_file_name: str = "btc_usdt_1d.csv") -> bool:
    """
    把 Binance 本地快取的 BTC 日線收盤價, 與 Kraken 獨立數據源在共同日期上逐日比對
    回傳是否通過(所有共同日期價差都在可疑上限以內) , 並印出比對摘要供人工判讀
    """
    cache_file_path = os.path.join(
        os.path.dirname(__file__), "cache", cache_file_name
    )
    if not os.path.exists(cache_file_path):
        raise FileNotFoundError(
            f"找不到快取 {cache_file_path}, 請先執行 fetchers/binance_fetcher.py"
        )
    binance_dataframe = pd.read_csv(cache_file_path, parse_dates=["open_time"])
    binance_close_by_date = binance_dataframe.set_index(
        binance_dataframe["open_time"].dt.normalize()
    )["close"]

    kraken_close_by_date = fetch_kraken_daily_close()

    # 只在兩個數據源都有的日期上比對, Kraken 免費端點只回最近約 720 天
    common_dates = binance_close_by_date.index.intersection(kraken_close_by_date.index)
    comparison = pd.DataFrame(
        {
            "binance_close": binance_close_by_date.loc[common_dates],
            "kraken_close": kraken_close_by_date.loc[common_dates],
        }
    ).sort_index()
    comparison["absolute_percentage_difference"] = (
        (comparison["binance_close"] - comparison["kraken_close"]).abs()
        / comparison["kraken_close"]
    )

    median_difference = comparison["absolute_percentage_difference"].median()
    maximum_difference = comparison["absolute_percentage_difference"].max()
    suspicious_days = comparison[
        comparison["absolute_percentage_difference"] > SUSPICIOUS_DIFFERENCE_THRESHOLD
    ]

    print(f"交叉驗證: Binance BTC/USDT 快取 vs Kraken BTC/USD 獨立數據源")
    print(f"共同比對日期數: {len(common_dates)} "
          f"({common_dates.min().date()} 至 {common_dates.max().date()})")
    print(f"收盤價差 中位數: {median_difference:.3%}, 最大: {maximum_difference:.3%}")
    print(f"容差參考: 正常價差應 < {CROSS_SOURCE_TOLERANCE:.0%}, "
          f"可疑門檻 > {SUSPICIOUS_DIFFERENCE_THRESHOLD:.0%}")

    is_valid = suspicious_days.empty
    if is_valid:
        print("通過: 本地快取與獨立數據源在所有共同日期上一致, 數據對應真實市場")
    else:
        print(f"警告: 有 {len(suspicious_days)} 天價差超過可疑門檻, 需人工調查:")
        print(suspicious_days.to_string())
    return is_valid


if __name__ == "__main__":
    validate_binance_cache_against_kraken()
