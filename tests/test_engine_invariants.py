"""
回測引擎不變量(invariant) 測試 — 用「性質」而非「逐筆核對真實數據」來驗證引擎正確性
人類只需 review 這些不變量的邏輯(固定, 可讀) , 機器則對所有數據窮舉驗證, 取代人工抽查 10 筆交易

不變量分兩類:
- 內部一致性: 引擎自身或引擎與輸入數據之間必須恆成立的關係(換手成本, 淨值守恆, 倉位上限等)
- 前視偏差防護: 用截斷法(metamorphic testing) 證明「未來數據不影響過去結果」, 這是人工無法做到的窮舉檢查

注意: 這些不變量只能證明「引擎與輸入數據一致」(verification) , 無法證明「輸入數據符合真實市場」
(validation) . 後者需要對數據源做一次外部錨定, 見 02_data/validate_against_independent_source.py
"""

import numpy as np
import pandas as pd
import pytest

from base import Strategy
from engine import BacktestEngine
from trend_following import TrendFollowingStrategy


@pytest.fixture
def oscillating_ohlcv():
    """
    人造的震盪加上緩慢上升的價格序列, 讓 EMA 快慢線多次交叉, 產生足夠多的進出場交易
    可控且確定, 適合窮舉驗證不變量; 正弦週期約 94 天, 400 天內約 4 個完整週期
    """
    time_index = np.arange(400)
    close_price = 100 + 20 * np.sin(time_index / 15) + time_index * 0.05
    close_series = pd.Series(close_price)
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2020-01-01", periods=400, freq="D"),
            "open": close_series,
            "high": close_series + 1,
            "low": close_series - 1,
            "close": close_series,
            "volume": pd.Series(np.full(400, 1000.0)),
        }
    )


@pytest.fixture
def strategy():
    return TrendFollowingStrategy(fast_span=12, slow_span=26, adx_threshold=0.0)


def test_dataset_actually_produces_multiple_trades(oscillating_ohlcv, strategy):
    # 前提檢查: 若數據跑不出足夠交易, 後面所有不變量都是空談, 先確保有多筆交易可驗
    result = BacktestEngine().run(oscillating_ohlcv, strategy)
    assert len(result.trades) >= 5


def test_all_trades_reconcile_with_source_prices(oscillating_ohlcv, strategy):
    """
    自動化版的「人工核對交易」: 對每一筆交易(不只 10 筆) 驗證
    進場價等於進場日的收盤價, 出場價等於出場日的收盤價
    進場日為信號當根 K 線(已 shift) , 其收盤價即引擎鎖定的進場成交價
    """
    result = BacktestEngine().run(oscillating_ohlcv, strategy)
    close_by_date = oscillating_ohlcv.set_index("open_time")["close"]
    for _, trade in result.trades.iterrows():
        expected_entry_close = close_by_date.loc[trade["entry_date"]]
        expected_exit_close = close_by_date.loc[trade["exit_date"]]
        assert np.isclose(trade["entry_price"], expected_entry_close)
        assert np.isclose(trade["exit_price"], expected_exit_close)


class SignalOnStrategy(Strategy):
    """測試用策略: 只在指定的那一根 K 線發出做多信號, 其餘時間空手, 用來精準定位「哪一根被交易」"""

    name = "signal_on_single_bar"

    def __init__(self, signal_bar_index: int) -> None:
        self.signal_bar_index = signal_bar_index

    def generate_signals(self, ohlcv_dataframe: pd.DataFrame) -> pd.Series:
        target_position = pd.Series(0, index=ohlcv_dataframe.index)
        target_position.iloc[self.signal_bar_index] = 1
        return target_position


def test_signal_is_executed_on_the_next_bar_not_the_signal_bar():
    """
    同根前視偏差防護: 第 t 根收盤產生的信號, 只能用來交易第 t+1 根的報酬, 不能交易第 t 根自己
    構造只有第 5 根有信號的策略, 驗證真正被持有, 賺到報酬的是第 6 根而非第 5 根
    這條不變量專門抓 shift(1) 時機錯誤; 截斷法(truncation) 抓不到這種同根時序錯誤(兩者互補)
    """
    close_price = pd.Series(
        [100, 101, 102, 103, 104, 140, 106, 107, 108, 109, 110, 111]
    )
    ohlcv_dataframe = pd.DataFrame(
        {
            "open_time": pd.date_range("2020-01-01", periods=len(close_price), freq="D"),
            "open": close_price,
            "high": close_price + 1,
            "low": close_price - 1,
            "close": close_price,
            "volume": pd.Series(np.full(len(close_price), 1000.0)),
        }
    )
    # 關掉手續費與滑點, 讓唯一的非零報酬完全來自被持有的那一根, 才能乾淨定位時序
    engine = BacktestEngine(fee_rate=0.0, slippage_rate=0.0)
    signal_bar_index = 5
    result = engine.run(ohlcv_dataframe, SignalOnStrategy(signal_bar_index))

    nonzero_return_indices = result.daily_return_percentage[
        result.daily_return_percentage != 0
    ].index
    # 有且只有一根 K 線被持有並產生報酬, 且它必須是信號的下一根(t+1) , 不是信號當根(t)
    assert list(nonzero_return_indices) == [signal_bar_index + 1]


@pytest.mark.parametrize("truncation_point", [50, 120, 200, 350])
def test_no_future_data_leakage_by_truncation(
    oscillating_ohlcv, strategy, truncation_point
):
    """
    前視偏差防護之一: 未來數據洩漏的窮舉證明(metamorphic test)
    砍掉截斷點之後的所有未來數據, 重跑引擎, 截斷點之前的每日策略報酬必須與完整數據的前綴逐值相同
    專門抓「第 t 根結果依賴到 t 之後數據」這類洩漏(如全樣本 max/min, 置中窗口, bfill, 全樣本擬合參數)
    抓不到同根時序錯誤(見上一條測試) , 兩條不變量互補, 合起來覆蓋前視偏差的兩大類
    這是人工逐筆核對永遠做不到的窮舉檢查, 卻是一條固定, 可讀的不變量
    """
    engine = BacktestEngine()
    full_result = engine.run(oscillating_ohlcv, strategy)
    truncated_result = engine.run(
        oscillating_ohlcv.iloc[:truncation_point], strategy
    )
    pd.testing.assert_series_equal(
        truncated_result.daily_return_percentage.reset_index(drop=True),
        full_result.daily_return_percentage.iloc[:truncation_point].reset_index(
            drop=True
        ),
        check_names=False,
    )


def test_equity_curve_is_consistent_with_daily_returns(oscillating_ohlcv, strategy):
    # 淨值守恆: 淨值曲線必須等於起始資金乘以每日淨報酬的累乘, 兩條路徑算出來不可分歧
    engine = BacktestEngine(initial_capital=10_000.0)
    result = engine.run(oscillating_ohlcv, strategy)
    reconstructed_equity = (
        1 + result.daily_return_percentage
    ).cumprod() * 10_000.0
    assert np.allclose(reconstructed_equity.values, result.equity_curve.values)


def test_higher_fees_never_increase_final_equity(oscillating_ohlcv, strategy):
    # 成本單調性: 手續費調高, 最終淨值只會更低或持平, 不可能更高
    low_fee_final = (
        BacktestEngine(fee_rate=0.0005)
        .run(oscillating_ohlcv, strategy)
        .equity_curve.iloc[-1]
    )
    high_fee_final = (
        BacktestEngine(fee_rate=0.005)
        .run(oscillating_ohlcv, strategy)
        .equity_curve.iloc[-1]
    )
    assert high_fee_final < low_fee_final


def test_higher_slippage_never_increases_final_equity(oscillating_ohlcv, strategy):
    # 成本單調性: 滑點調高, 最終淨值只會更低或持平
    low_slippage_final = (
        BacktestEngine(slippage_rate=0.0005)
        .run(oscillating_ohlcv, strategy)
        .equity_curve.iloc[-1]
    )
    high_slippage_final = (
        BacktestEngine(slippage_rate=0.005)
        .run(oscillating_ohlcv, strategy)
        .equity_curve.iloc[-1]
    )
    assert high_slippage_final < low_slippage_final


def test_position_fraction_never_exceeds_cap(oscillating_ohlcv, strategy):
    # 倉位上限: 每一筆交易的倉位佔比都不得超過設定上限, 現貨不做槓桿
    maximum_fraction = 0.5
    result = BacktestEngine(max_position_fraction=maximum_fraction).run(
        oscillating_ohlcv, strategy
    )
    assert (result.trades["position_fraction"] <= maximum_fraction + 1e-9).all()


def test_engine_run_is_deterministic(oscillating_ohlcv, strategy):
    # 決定性: 相同輸入必須產生完全相同的輸出, 引擎不得引入任何隨機性
    engine = BacktestEngine()
    first_result = engine.run(oscillating_ohlcv, strategy)
    second_result = engine.run(oscillating_ohlcv, strategy)
    pd.testing.assert_series_equal(
        first_result.equity_curve, second_result.equity_curve
    )
