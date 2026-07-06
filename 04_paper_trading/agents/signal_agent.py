"""
Signal agent — 用 exp_002 凍結參數跑趨勢跟蹤(trend following) 策略, 決定「現在」該有的目標倉位
直接從 exp_002_ema_adx/config.py import 凍結參數, 不重複宣告字典, 確保紙上交易與回測參數永遠一致
"""
import os
import sys
from datetime import timezone

import pandas as pd

_agents_directory = os.path.dirname(os.path.abspath(__file__))
_paper_trading_directory = os.path.dirname(_agents_directory)
_repository_root = os.path.dirname(_paper_trading_directory)
for _module_subdirectory in ["01_indicators", "02_strategies", "03_backtest"]:
    sys.path.insert(0, os.path.join(_repository_root, "03_research", _module_subdirectory))
sys.path.insert(
    0, os.path.join(_repository_root, "03_research", "04_experiments", "exp_002_ema_adx")
)
sys.path.insert(0, _paper_trading_directory)

from config import ENGINE_PARAMS, STRATEGY_PARAMS  # noqa: E402
from trend_following import TrendFollowingStrategy  # noqa: E402
from volatility import average_true_range  # noqa: E402

from events import SignalEvent  # noqa: E402

# 重新匯出凍結參數, 讓 run_once.py 與測試不用各自再走一次 exp_002 config.py 的路徑手續
FROZEN_STRATEGY_PARAMETERS = STRATEGY_PARAMS
FROZEN_ENGINE_PARAMETERS = ENGINE_PARAMS

_FROZEN_STRATEGY = TrendFollowingStrategy(**STRATEGY_PARAMS)


def decide(ohlcv_dataframe: pd.DataFrame, symbol: str) -> SignalEvent:
    """
    對輸入的 OHLCV(開高低收量) 數據跑凍結的 exp_002 策略, 取最後一列的目標倉位當作「現在」的決策
    參數 ohlcv_dataframe: 至少需涵蓋策略暖身期, 由 data_agent.fetch_latest_candles 提供
    回傳 SignalEvent, target_position 為 0(空手) 或 1(多單)
    """
    target_position_series = _FROZEN_STRATEGY.generate_signals(ohlcv_dataframe)
    average_true_range_series = average_true_range(
        ohlcv_dataframe["high"],
        ohlcv_dataframe["low"],
        ohlcv_dataframe["close"],
        FROZEN_ENGINE_PARAMETERS["atr_period"],
    )
    latest_row = ohlcv_dataframe.iloc[-1]
    return SignalEvent(
        symbol=symbol,
        target_position=int(target_position_series.iloc[-1]),
        as_of_timestamp=latest_row["open_time"].to_pydatetime().replace(tzinfo=timezone.utc),
        latest_close_price=float(latest_row["close"]),
        latest_average_true_range=float(average_true_range_series.iloc[-1]),
    )
