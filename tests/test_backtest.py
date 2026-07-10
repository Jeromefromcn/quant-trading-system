"""
回測引擎單元測試. 驗證引擎的關鍵行為: 前視偏差防護, 交易成本, 樣本劃分, 指標計算
用建構好的合成數據(而非真實市場數據) , 讓每個性質可獨立驗證
"""

import numpy as np
import pandas as pd
import pytest

from base import Strategy
from engine import BacktestEngine, split_in_sample_out_of_sample
from metrics import annualized_sharpe_ratio, maximum_drawdown, profit_factor


class AlwaysLongStrategy(Strategy):
    """永遠持有多單的策略, 等效於買入並持有(Buy and Hold) , 用於驗證引擎基本正確性"""

    name = "always_long"

    def generate_signals(self, ohlcv_dataframe):
        return pd.Series(1, index=ohlcv_dataframe.index)


class NeverLongStrategy(Strategy):
    """永遠空手的策略, 淨值應紋絲不動"""

    name = "never_long"

    def generate_signals(self, ohlcv_dataframe):
        return pd.Series(0, index=ohlcv_dataframe.index)


@pytest.fixture
def steady_uptrend_ohlcv():
    close_price = pd.Series(np.linspace(100, 200, 100))
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2025-01-01", periods=100, freq="D"),
            "open": close_price,
            "high": close_price + 1,
            "low": close_price - 1,
            "close": close_price,
            "volume": pd.Series(np.full(100, 1000.0)),
        }
    )


def test_never_long_keeps_capital_flat(steady_uptrend_ohlcv):
    engine = BacktestEngine(initial_capital=10_000.0)
    result = engine.run(steady_uptrend_ohlcv, NeverLongStrategy())
    assert np.isclose(result.equity_curve.iloc[-1], 10_000.0)
    assert result.metrics["number_of_trades"] == 0


def test_always_long_grows_in_uptrend(steady_uptrend_ohlcv):
    # 無槓桿上限下上漲趨勢做多, 最終淨值必須高於起始資金
    engine = BacktestEngine(initial_capital=10_000.0, max_position_fraction=1.0)
    result = engine.run(steady_uptrend_ohlcv, AlwaysLongStrategy())
    assert result.equity_curve.iloc[-1] > 10_000.0


def test_no_lookahead_first_bar_return_is_zero(steady_uptrend_ohlcv):
    # 前視偏差防護: 信號位移一天後, 第一根 K 線不可能有持倉, 當天策略報酬必須為 0
    engine = BacktestEngine()
    result = engine.run(steady_uptrend_ohlcv, AlwaysLongStrategy())
    assert result.daily_return_percentage.iloc[0] == 0


def test_fees_reduce_return(steady_uptrend_ohlcv):
    # 同一策略, 有手續費與滑點時最終淨值必須低於零成本時
    zero_cost_engine = BacktestEngine(fee_rate=0.0, slippage_rate=0.0)
    with_cost_engine = BacktestEngine(fee_rate=0.001, slippage_rate=0.0005)
    zero_cost_result = zero_cost_engine.run(steady_uptrend_ohlcv, AlwaysLongStrategy())
    with_cost_result = with_cost_engine.run(steady_uptrend_ohlcv, AlwaysLongStrategy())
    assert with_cost_result.equity_curve.iloc[-1] < zero_cost_result.equity_curve.iloc[-1]


def test_split_in_sample_out_of_sample_ratio(steady_uptrend_ohlcv):
    in_sample, out_of_sample = split_in_sample_out_of_sample(
        steady_uptrend_ohlcv, in_sample_ratio=0.7
    )
    assert len(in_sample) == 70
    assert len(out_of_sample) == 30
    # 樣本外必須是時間上的後段, 不能與樣本內重疊
    assert out_of_sample["open_time"].iloc[0] > in_sample["open_time"].iloc[-1]


def test_trade_summary_records_entry_and_exit(steady_uptrend_ohlcv):
    engine = BacktestEngine()
    result = engine.run(steady_uptrend_ohlcv, AlwaysLongStrategy())
    # 全程做多只會有一筆連續交易
    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["entry_price"] < trade["exit_price"]
    assert trade["holding_days"] > 0


def test_trade_entry_price_is_signal_bar_close(steady_uptrend_ohlcv):
    # 信號已 shift(1) , 持倉在進場信號當根 K 線收盤成交, 記錄的進場價應等於場首日前一根的收盤價
    engine = BacktestEngine()
    result = engine.run(steady_uptrend_ohlcv, AlwaysLongStrategy())
    trade = result.trades.iloc[0]
    # AlwaysLong 在第 0 根產生信號, 第 1 根起持倉, 進場成交價即第 0 根收盤價
    assert np.isclose(trade["entry_price"], steady_uptrend_ohlcv["close"].iloc[0])
    assert trade["entry_date"] == steady_uptrend_ohlcv["open_time"].iloc[0]


def test_metrics_helpers_on_known_series():
    # 淨值單調下跌, 最大回撤應為負且等於總跌幅
    declining_equity = pd.Series([100.0, 90.0, 81.0])
    assert maximum_drawdown(declining_equity) < 0
    # 零波動報酬的 Sharpe 定義為 0, 不應拋出除以零錯誤
    assert annualized_sharpe_ratio(pd.Series([0.0, 0.0, 0.0])) == 0.0
    # 沒有虧損交易時盈虧比為無限大
    assert profit_factor(pd.Series([0.1, 0.2])) == float("inf")
