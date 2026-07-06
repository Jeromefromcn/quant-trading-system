"""signal_agent.decide 的單元測試 — 用手造的確定性價格序列驗證多單/空手判斷與事件欄位"""
import numpy as np
import pandas as pd

import signal_agent


def _make_ohlcv(closes) -> pd.DataFrame:
    """比照 tests/test_trailing_stop.py 的手法: 由收盤價序列造 OHLCV, high/low 取 ±1 固定區間"""
    close_price = pd.Series(closes, dtype=float)
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2020-01-01", periods=len(close_price), freq="D"),
            "open": close_price,
            "high": close_price + 1.0,
            "low": close_price - 1.0,
            "close": close_price,
            "volume": pd.Series(np.full(len(close_price), 1000.0)),
        }
    )


def test_decide_reports_long_when_strong_uptrend():
    # 持續上漲 120 天, 快線在慢線之上且趨勢夠強(ADX 應高於凍結門檻 25) , 目標倉位應為多單(1)
    closes = np.linspace(100, 400, 120)
    ohlcv_dataframe = _make_ohlcv(closes)

    signal_event = signal_agent.decide(ohlcv_dataframe, "BTCUSDT")

    assert signal_event.symbol == "BTCUSDT"
    assert signal_event.target_position == 1
    assert signal_event.latest_close_price == closes[-1]
    assert signal_event.latest_average_true_range > 0
    assert signal_event.as_of_timestamp.date() == ohlcv_dataframe["open_time"].iloc[-1].date()


def test_decide_reports_flat_when_price_is_flat():
    # 完全走平 120 天, 快慢線相等無交叉, 目標倉位應為空手(0) , 與 ADX 高低無關
    closes = np.full(120, 100.0)
    ohlcv_dataframe = _make_ohlcv(closes)

    signal_event = signal_agent.decide(ohlcv_dataframe, "BTCUSDT")

    assert signal_event.target_position == 0


def test_decide_reports_flat_when_crossover_occurs_but_adx_is_below_threshold():
    # 有淨上漲的震盪走勢: 快線持續在慢線之上(純 EMA 交叉會判多) , 但反覆震盪讓 ADX 維持在低檔(遠低於門檻 25) ,
    # 這是 exp_002 相對 exp_001 的核心差異 — 濾掉盤整假突破, 必須驗證這個過濾確實生效
    time_index = np.arange(120)
    closes = 100 + 0.05 * time_index + 3.0 * np.sin(time_index * 0.9)
    ohlcv_dataframe = _make_ohlcv(closes)

    signal_event = signal_agent.decide(ohlcv_dataframe, "BTCUSDT")

    assert signal_event.target_position == 0
