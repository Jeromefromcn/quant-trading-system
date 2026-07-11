"""
Stock data agent: 拉取最新美股日線, 供 signal_agent 產生即時信號用.
重用 02_data/fetchers/alpaca_fetcher.py 的 fetch_full_history_daily_bars(已測試過的抓取邏輯), 以
今天往回推 LOOKBACK_CALENDAR_DAYS 個日曆天當 start_date, 取回後只保留最後 lookback_bars 根,
不重寫一套抓取邏輯, 與加密貨幣側 data_agent.py 重用既有抓取程式碼路徑的精神一致.
"""
import os
import sys
from datetime import date, timedelta

import pandas as pd

_agents_directory = os.path.dirname(os.path.abspath(__file__))
_paper_trading_directory = os.path.dirname(_agents_directory)
_repository_root = os.path.dirname(_paper_trading_directory)
sys.path.insert(0, os.path.join(_repository_root, "02_data", "fetchers"))
from alpaca_fetcher import fetch_full_history_daily_bars  # noqa: E402

# 暖身期保守值, 與加密貨幣側 data_agent.DEFAULT_LOOKBACK_BARS 同一套理由:
# exp_002 的 slow_span=26 / adx_period=14 皆為威爾德式平滑(Wilder smoothing), 100 根後殘餘權重
# 已降到千分之一以下, 讓即時計算的指標值更貼近回測用全歷史算出的版本
DEFAULT_LOOKBACK_BARS = 100
# 100 個交易日約需回推 140 個日曆天(週末/假日不開盤); 200 天留了充足緩衝, 確保抓得到足夠根數
LOOKBACK_CALENDAR_DAYS = 200


def fetch_latest_daily_bars(symbol: str, lookback_bars: int = DEFAULT_LOOKBACK_BARS) -> pd.DataFrame:
    """
    拉取最近 lookback_bars 根已收盤日線, 足夠 exp_002 策略指標暖身
    回傳按時間升冪排列, 只含核心 OHLCV(開高低收量) 欄位的 DataFrame
    拋出 ValueError: 若抓到的根數少於 lookback_bars(數據不足, 不該在殘缺窗口上硬算指標)
    """
    start_date = (date.today() - timedelta(days=LOOKBACK_CALENDAR_DAYS)).isoformat()
    ohlcv_dataframe = fetch_full_history_daily_bars(symbol, start_date=start_date)
    if len(ohlcv_dataframe) < lookback_bars:
        raise ValueError(
            f"{symbol} 只抓到 {len(ohlcv_dataframe)} 根已收盤日線, "
            f"少於暖身所需的 {lookback_bars} 根"
        )
    return ohlcv_dataframe.tail(lookback_bars).reset_index(drop=True)
