"""
Binance 歷史 K 線抓取器 — 從 Binance 公開行情 API 分頁抓取指定交易對的完整歷史日線
公開行情端點不需要 API Key. Binance 單次最多回傳 1000 根 K 線, 需用 startTime 分頁往後累積,
直到抓到最新一根. 抓下來的數據存到本地 cache(被 gitignore) , 供研究層重複讀取, 不必每次重打 API
本檔的請求與解析函式 (request_klines_batch, parse_klines_to_ohlcv_dataframe, drop_unclosed_last_candle)
也被 04_paper_trading/agents/data_agent.py 重用, 供即時抓取最新 K 線, 兩處共用同一段已測試邏輯
"""

import os
import time

import pandas as pd
import requests

BINANCE_KLINES_ENDPOINT = "https://api.binance.com/api/v3/klines"
# 單次請求上限, Binance 官方硬性限制為 1000 根
MAX_KLINES_PER_REQUEST = 1000

# Binance 回傳的每根 K 線是無欄位名的陣列, 按官方文件順序對應成有意義的欄位名
KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]
PRICE_AND_VOLUME_COLUMNS = ["open", "high", "low", "close", "volume"]


def request_klines_batch(
    symbol: str, interval: str, limit: int, start_time_milliseconds: int | None = None
) -> list:
    """
    打一次 Binance 公開 K 線端點, 回傳原始 (未解析) 的 K 線陣列列表
    參數 start_time_milliseconds 為 None 時, Binance 回傳「最新」的 limit 根 K 線 (不分頁, 供即時抓取用)
    給定 start_time_milliseconds 時, 回傳從該時間點開始的 limit 根 (供歷史分頁抓取用)
    """
    request_parameters = {"symbol": symbol, "interval": interval, "limit": limit}
    if start_time_milliseconds is not None:
        request_parameters["startTime"] = start_time_milliseconds
    response = requests.get(BINANCE_KLINES_ENDPOINT, params=request_parameters, timeout=30)
    response.raise_for_status()
    return response.json()


def parse_klines_to_ohlcv_dataframe(klines_batch: list) -> pd.DataFrame:
    """
    把 Binance 原始 K 線陣列列表解析成核心 OHLCV(開高低收量) 欄位 + close_time 的 DataFrame, 時間升冪排列
    保留 close_time 供 drop_unclosed_last_candle 判斷最後一根是否已收盤, 該函式回傳前會將其移除
    """
    kline_dataframe = pd.DataFrame(klines_batch, columns=KLINE_COLUMNS)
    kline_dataframe["open_time"] = pd.to_datetime(kline_dataframe["open_time"], unit="ms")
    kline_dataframe[PRICE_AND_VOLUME_COLUMNS] = kline_dataframe[
        PRICE_AND_VOLUME_COLUMNS
    ].astype(float)
    kline_dataframe["close_time"] = pd.to_datetime(kline_dataframe["close_time"], unit="ms")
    return kline_dataframe[
        ["open_time", "open", "high", "low", "close", "volume", "close_time"]
    ].copy()


def drop_unclosed_last_candle(ohlcv_dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    最後一根 K 線通常尚未收盤(仍在跳動) , 為避免用到不完整數據, 若尚未收盤則移除
    回傳前移除 close_time 輔助欄位, 只留核心 OHLCV 欄位, 並重設索引
    """
    last_close_time = ohlcv_dataframe["close_time"].iloc[-1]
    current_utc_time = pd.Timestamp.now("UTC").tz_localize(None)
    if last_close_time > current_utc_time:
        ohlcv_dataframe = ohlcv_dataframe.iloc[:-1]
    return ohlcv_dataframe.drop(columns=["close_time"]).reset_index(drop=True)


def fetch_full_history_klines(
    symbol: str, interval: str = "1d", request_pause_seconds: float = 0.2
) -> pd.DataFrame:
    """
    分頁抓取某交易對從上市至今的完整歷史 K 線
    參數 symbol: 交易對代號, 例如 "BTCUSDT"
    參數 interval: K 線週期, 例如 "1d"(日線) , "4h"(4 小時線)
    參數 request_pause_seconds: 每次請求之間的暫停, 禮貌性避免觸發 Binance 速率限制
    回傳只含核心 OHLCV 欄位的 DataFrame, 時間升冪排列, 已去除最後一根未收盤 K 線
    """
    accumulated_rows = []
    # startTime 設為 0, Binance 會自動從該交易對真正上市的第一根 K 線開始回傳
    next_start_time_milliseconds = 0

    while True:
        klines_batch = request_klines_batch(
            symbol, interval, MAX_KLINES_PER_REQUEST, next_start_time_milliseconds
        )
        if not klines_batch:
            break

        accumulated_rows.extend(klines_batch)
        # 下一頁從這一頁最後一根 K 線的開盤時間 + 1 毫秒開始, 避免重複抓到同一根
        last_open_time_milliseconds = klines_batch[-1][0]
        next_start_time_milliseconds = last_open_time_milliseconds + 1

        # 回傳數量不足一整頁, 代表已經抓到最新一根, 結束分頁
        if len(klines_batch) < MAX_KLINES_PER_REQUEST:
            break
        time.sleep(request_pause_seconds)

    ohlcv_dataframe = parse_klines_to_ohlcv_dataframe(accumulated_rows)
    return drop_unclosed_last_candle(ohlcv_dataframe)


def save_to_cache(ohlcv_dataframe: pd.DataFrame, cache_file_name: str) -> str:
    """把抓取結果存到 02_data/cache/ 目錄, 回傳實際存檔路徑; cache 目錄由 gitignore 排除"""
    cache_directory = os.path.join(os.path.dirname(__file__), "..", "cache")
    os.makedirs(cache_directory, exist_ok=True)
    cache_file_path = os.path.join(cache_directory, cache_file_name)
    ohlcv_dataframe.to_csv(cache_file_path, index=False)
    return cache_file_path


if __name__ == "__main__":
    # 直接執行時, 抓取研究層 Round 1 基準需要的加密貨幣日線: BTC/USDT 與 ETH/USDT
    for trading_symbol, output_file_name in [
        ("BTCUSDT", "btc_usdt_1d.csv"),
        ("ETHUSDT", "eth_usdt_1d.csv"),
    ]:
        history_dataframe = fetch_full_history_klines(trading_symbol, "1d")
        saved_path = save_to_cache(history_dataframe, output_file_name)
        print(
            f"{trading_symbol}: 抓取 {len(history_dataframe)} 根日線 "
            f"({history_dataframe['open_time'].iloc[0].date()} 至 "
            f"{history_dataframe['open_time'].iloc[-1].date()}) , 已存到 {saved_path}"
        )
