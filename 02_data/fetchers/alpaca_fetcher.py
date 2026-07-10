"""
Alpaca 美股歷史日線抓取器: 從 Alpaca Market Data API 抓取指定股票的調整後歷史日線
需要 Alpaca API Key(從 .env 讀取, 不入 Git) . 免費方案使用 IEX 數據源, 歷史可回溯到約 2016 年
使用 adjustment=all 取得還原權息後的調整價格, 回測股票時必須用調整價才不會被除權除息扭曲報酬
Alpaca 單次最多回傳 10000 根, 超過時用 next_page_token 分頁往後累積
"""

import os

import pandas as pd
import requests
from dotenv import load_dotenv

# 從專案根目錄的 .env 讀取 Alpaca 憑證; .env 已被 gitignore, 不會外洩
_repository_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(_repository_root, ".env"))

ALPACA_STOCK_BARS_ENDPOINT = "https://data.alpaca.markets/v2/stocks/{symbol}/bars"
MAX_BARS_PER_REQUEST = 10000

# Alpaca 回傳的欄位縮寫對應到可讀的 OHLCV(開高低收量) 欄位名
ALPACA_BAR_FIELD_TO_COLUMN = {
    "t": "open_time",
    "o": "open",
    "h": "high",
    "l": "low",
    "c": "close",
    "v": "volume",
}


def _build_authentication_headers() -> dict:
    """組出 Alpaca 要求的認證標頭, 缺少憑證時直接報錯提示先設定 .env"""
    api_key = os.getenv("ALPACA_PAPER_API_KEY")
    secret_key = os.getenv("ALPACA_PAPER_SECRET_KEY")
    if not api_key or not secret_key or "your_" in api_key:
        raise RuntimeError(
            "缺少 Alpaca 憑證, 請先在 .env 填入 ALPACA_PAPER_API_KEY 與 ALPACA_PAPER_SECRET_KEY"
        )
    return {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}


def fetch_full_history_daily_bars(
    symbol: str, start_date: str = "2016-01-01", data_feed: str = "iex"
) -> pd.DataFrame:
    """
    抓取某股票從 start_date 至今的完整調整後歷史日線
    參數 symbol: 股票代號, 例如 "SPY"
    參數 start_date: 起始日期(YYYY-MM-DD) , 免費 IEX 數據源最早約到 2016 年
    參數 data_feed: 數據源, 免費方案用 "iex"
    回傳只含核心 OHLCV 欄位的 DataFrame, 時間升冪排列
    """
    authentication_headers = _build_authentication_headers()
    accumulated_bars = []
    next_page_token = None

    while True:
        request_parameters = {
            "timeframe": "1Day",
            "start": start_date,
            "limit": MAX_BARS_PER_REQUEST,
            "adjustment": "all",
            "feed": data_feed,
        }
        if next_page_token is not None:
            request_parameters["page_token"] = next_page_token

        response = requests.get(
            ALPACA_STOCK_BARS_ENDPOINT.format(symbol=symbol),
            params=request_parameters,
            headers=authentication_headers,
            timeout=30,
        )
        response.raise_for_status()
        response_body = response.json()
        accumulated_bars.extend(response_body.get("bars") or [])

        # Alpaca 用 next_page_token 標示是否還有下一頁, 為 None 代表已抓完
        next_page_token = response_body.get("next_page_token")
        if next_page_token is None:
            break

    bars_dataframe = pd.DataFrame(accumulated_bars)
    bars_dataframe = bars_dataframe.rename(columns=ALPACA_BAR_FIELD_TO_COLUMN)
    bars_dataframe["open_time"] = pd.to_datetime(bars_dataframe["open_time"]).dt.tz_localize(
        None
    )
    ohlcv_dataframe = bars_dataframe[
        ["open_time", "open", "high", "low", "close", "volume"]
    ].copy()
    return ohlcv_dataframe.reset_index(drop=True)


def save_to_cache(ohlcv_dataframe: pd.DataFrame, cache_file_name: str) -> str:
    """把抓取結果存到 02_data/cache/ 目錄, 回傳實際存檔路徑; cache 目錄由 gitignore 排除"""
    cache_directory = os.path.join(os.path.dirname(__file__), "..", "cache")
    os.makedirs(cache_directory, exist_ok=True)
    cache_file_path = os.path.join(cache_directory, cache_file_name)
    ohlcv_dataframe.to_csv(cache_file_path, index=False)
    return cache_file_path


if __name__ == "__main__":
    # 直接執行時, 抓取研究層 Round 1 基準需要的美股日線: SPY 與 QQQ
    for stock_symbol, output_file_name in [
        ("SPY", "spy_1d.csv"),
        ("QQQ", "qqq_1d.csv"),
    ]:
        history_dataframe = fetch_full_history_daily_bars(stock_symbol)
        saved_path = save_to_cache(history_dataframe, output_file_name)
        print(
            f"{stock_symbol}: 抓取 {len(history_dataframe)} 根日線 "
            f"({history_dataframe['open_time'].iloc[0].date()} 至 "
            f"{history_dataframe['open_time'].iloc[-1].date()}) , 已存到 {saved_path}"
        )
