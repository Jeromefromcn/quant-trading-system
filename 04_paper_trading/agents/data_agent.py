"""
Data agent: 拉取最新 K 線, 供 signal_agent 產生即時信號用
重用 02_data/fetchers/binance_fetcher.py 的請求與解析邏輯 (request_klines_batch,
parse_klines_to_ohlcv_dataframe, drop_unclosed_last_candle) , 不重寫一份, 讓歷史抓取與即時抓取
共用同一段已測試過的程式碼路徑
"""
import os
import sys

import pandas as pd

_agents_directory = os.path.dirname(os.path.abspath(__file__))
_paper_trading_directory = os.path.dirname(_agents_directory)
_repository_root = os.path.dirname(_paper_trading_directory)
sys.path.insert(0, os.path.join(_repository_root, "02_data", "fetchers"))
from binance_fetcher import (  # noqa: E402
    drop_unclosed_last_candle,
    parse_klines_to_ohlcv_dataframe,
    request_klines_batch,
)

# 暖身期保守值: exp_002 的 slow_span=26 / adx_period=14 皆為威爾德式平滑(Wilder smoothing) ,
# 對更早數據的權重會隨窗口拉長而指數衰減但不會歸零; 100 根後殘餘權重已降到千分之一以下,
# 比嚴格暖身期(約 26-40 根) 更保守, 讓即時計算的指標值更貼近回測用全歷史算出的版本
DEFAULT_LOOKBACK_BARS = 100


def fetch_latest_candles(
    symbol: str, interval: str = "1d", lookback_bars: int = DEFAULT_LOOKBACK_BARS
) -> pd.DataFrame:
    """
    拉取最近 lookback_bars 根已收盤 K 線, 足夠 exp_002 策略指標暖身
    回傳按時間升冪排列, 只含核心 OHLCV(開高低收量) 欄位的 DataFrame
    拋出 ValueError: 若已收盤根數少於 lookback_bars(數據不足, 不該在殘缺窗口上硬算指標)
    """
    # 多拉一根: 最後一根若尚未收盤會被丟棄, 需要多要一根才能保證丟棄後仍有 lookback_bars 根
    raw_klines = request_klines_batch(symbol, interval, limit=lookback_bars + 1)
    ohlcv_dataframe = parse_klines_to_ohlcv_dataframe(raw_klines)
    ohlcv_dataframe = drop_unclosed_last_candle(ohlcv_dataframe)
    if len(ohlcv_dataframe) < lookback_bars:
        raise ValueError(
            f"{symbol} 只抓到 {len(ohlcv_dataframe)} 根已收盤 K 線, "
            f"少於暖身所需的 {lookback_bars} 根"
        )
    return ohlcv_dataframe
