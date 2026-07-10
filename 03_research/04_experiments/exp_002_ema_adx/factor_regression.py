"""
exp_002 因子迴歸驗證 (factor regression): 檢驗 exp_002 的報酬是市場已知風險溢價 (risk premium) 的
beta 曝險, 還是控制已知因子後仍然顯著為正的 alpha.

背景 (見 STRATEGY_LOG.md 2026-07-06 alpha/beta 討論): exp_002 (EMA 雙均線 + ADX 濾網) 樣本外
Sharpe 0.97, 四個市場都沒過 1.0. 推論是這個報酬來自動能 / 趨勢溢價 (momentum / trend premium,
一種有學術文獻支持的系統性風險因子) , 不是無人發現的秘密 alpha. 本腳本直接檢驗這個推論:

    exp_002 淨報酬_t = alpha + beta_市場 * 買入持有報酬_t + beta_動能 * 通用動能因子報酬_t + 殘差_t

若 alpha 在放入動能因子後塌縮並失去統計顯著性, 支持 exp_002 是 beta 不是 alpha 的判斷.

因子建構原則 (避免循環論證, circular reasoning): 動能因子必須獨立於 exp_002 自己的訊號建構,
否則迴歸只是拿自己解釋自己. 採用學界時序動能 (TSMOM, time-series momentum, 見 Moskowitz,
Ooi, Pedersen 2012) 的標準做法: 落後 365 天 (加密貨幣年化慣例, 對應過去 12 個月) 報酬為正則
持有多單, 否則空手 (long-only, 呼應 exp_002 現貨不放空) . 這與 exp_002 用的 EMA 交叉 + ADX 完全
是不同的訊號建構, 是真正獨立的通用趨勢代理, 不是 exp_002 自己的訊號改個名字.

統計方法: 傳統 OLS 的 t 檢定會低估標準誤 (standard error) , 因為策略報酬存在序列相關
(serial correlation, 同一筆交易橫跨多天, 報酬不獨立) . 改用 Newey-West (1987) 提出的
HAC (heteroskedasticity and autocorrelation consistent, 異方差與序列相關穩健) 標準誤,
是金融時間序列迴歸的業界慣例. 本檔未使用 statsmodels/scipy (未在 requirements.txt 中) ,
以 numpy 手動實作 OLS 與 Newey-West 公式.

執行: python factor_regression.py (需先 cd 到本檔所在目錄, 或直接用完整路徑執行)
"""

import math
import os
import sys

import numpy as np
import pandas as pd

_experiment_directory = os.path.dirname(os.path.abspath(__file__))
_research_directory = os.path.dirname(os.path.dirname(_experiment_directory))
_repository_root = os.path.dirname(_research_directory)
# 目錄名以數字開頭無法當成 Python 套件, 手動把回測層, 策略層, 指標層加入模組搜尋路徑 (與 run_experiment.py 一致)
for _module_subdirectory in ["01_indicators", "02_strategies", "03_backtest"]:
    sys.path.insert(0, os.path.join(_research_directory, _module_subdirectory))
from engine import BacktestEngine, split_in_sample_out_of_sample  # noqa: E402
from trend_following import TrendFollowingStrategy  # noqa: E402

# 與 exp_002/config.py 完全相同的凍結參數, 不得為了這次驗證另外調參
STRATEGY_PARAMETERS = {
    "fast_span": 12,
    "slow_span": 26,
    "adx_period": 14,
    "adx_threshold": 25.0,
}
ENGINE_PARAMETERS = {
    "initial_capital": 10_000.0,
    "risk_per_trade_percentage": 0.01,
    "atr_stop_multiplier": 2.0,
    "atr_period": 14,
    "fee_rate": 0.001,
    "slippage_rate": 0.0005,
    "max_position_fraction": 1.0,
    "trading_days_per_year": 365,
}
IN_SAMPLE_RATIO = 0.7

# 通用動能因子的落後窗口: 365 天呼應 TSMOM 文獻慣用的過去 12 個月, 且與本專案加密貨幣年化天數一致
MOMENTUM_LOOKBACK_DAYS = 365
TRADING_DAYS_PER_YEAR = 365


def load_btc_ohlcv_dataframe() -> pd.DataFrame:
    """讀取與 exp_002 完全相同的快取數據, 保留原始整數索引 (供樣本外切分後對齊使用)"""
    dataset_path = os.path.join(_repository_root, "02_data", "cache", "btc_usdt_1d.csv")
    return pd.read_csv(dataset_path, parse_dates=["open_time"])


def compute_market_factor_return(ohlcv_dataframe: pd.DataFrame) -> pd.Series:
    """市場因子: 買入持有 (buy-and-hold) 當日報酬, 不依賴任何策略訊號, 風險溢利率簡化為 0
    (BTC 日波動遠大於無風險利率, 忽略無風險利率是這類分析的常見簡化)"""
    return ohlcv_dataframe["close"].pct_change().fillna(0)


def compute_momentum_factor_return(
    ohlcv_dataframe: pd.DataFrame, market_return: pd.Series
) -> pd.Series:
    """通用動能因子 (TSMOM 風格, 與 exp_002 自身訊號無關) : 落後 365 天報酬 > 0 則多單, 否則空手
    用前一天已知的訊號交易當天報酬 (shift(1)) , 與引擎相同的前視偏差防護慣例"""
    trailing_return = ohlcv_dataframe["close"].pct_change(MOMENTUM_LOOKBACK_DAYS)
    is_trailing_return_positive = (trailing_return > 0).fillna(False).astype(int)
    executed_momentum_position = is_trailing_return_positive.shift(1).fillna(0)
    return executed_momentum_position * market_return


def compute_newey_west_lag(number_of_observations: int) -> int:
    """Newey-West (1994) 自動落後期數建議公式: floor(4 * (T/100)^(2/9))"""
    return int(np.floor(4 * (number_of_observations / 100) ** (2 / 9)))


def _normal_cumulative_distribution(z_score: float) -> float:
    """標準常態分布的累積分布函數 (CDF) , 用 math.erf 手算, 避免額外依賴 scipy"""
    return 0.5 * (1 + math.erf(z_score / math.sqrt(2)))


def run_ols_with_newey_west(design_matrix: np.ndarray, target: np.ndarray, lag: int) -> dict:
    """
    OLS 迴歸 + Newey-West(1987) HAC 標準誤
    回傳: 係數 (coefficients), HAC 標準誤, t 統計量, 兩尾 p 值 (常態近似), R 平方
    """
    number_of_observations = design_matrix.shape[0]
    coefficients, _, _, _ = np.linalg.lstsq(design_matrix, target, rcond=None)
    residuals = target - design_matrix @ coefficients

    # u_t = x_t * e_t (逐筆的分數向量), HAC 的核心是這些分數的自我與跨期共變異數
    scores = design_matrix * residuals[:, None]
    gramian_matrix = design_matrix.T @ design_matrix / number_of_observations

    score_covariance = scores.T @ scores / number_of_observations
    for lag_order in range(1, lag + 1):
        lagged_cross_product = (
            scores[lag_order:].T @ scores[:-lag_order] / number_of_observations
        )
        bartlett_weight = 1 - lag_order / (lag + 1)
        score_covariance += bartlett_weight * (lagged_cross_product + lagged_cross_product.T)

    gramian_inverse = np.linalg.inv(gramian_matrix)
    coefficient_covariance = (
        gramian_inverse @ score_covariance @ gramian_inverse / number_of_observations
    )
    standard_errors = np.sqrt(np.diag(coefficient_covariance))
    t_statistics = coefficients / standard_errors
    p_values = np.array(
        [2 * (1 - _normal_cumulative_distribution(abs(t))) for t in t_statistics]
    )

    total_sum_of_squares = np.sum((target - target.mean()) ** 2)
    residual_sum_of_squares = np.sum(residuals**2)
    r_squared = 1 - residual_sum_of_squares / total_sum_of_squares

    return {
        "coefficients": coefficients,
        "standard_errors": standard_errors,
        "t_statistics": t_statistics,
        "p_values": p_values,
        "r_squared": r_squared,
        "number_of_observations": number_of_observations,
        "lag": lag,
    }


def _annualize_daily_alpha(daily_alpha: float) -> float:
    return (1 + daily_alpha) ** TRADING_DAYS_PER_YEAR - 1


def _print_regression_report(
    title: str, strategy_return: pd.Series, market_return: pd.Series, momentum_return: pd.Series
) -> None:
    number_of_observations = len(strategy_return)
    lag = compute_newey_west_lag(number_of_observations)

    print(f"\n{'=' * 78}\n{title} (N={number_of_observations} 天, Newey-West 落後期數={lag})\n{'=' * 78}")

    market_only_design_matrix = np.column_stack(
        [np.ones(number_of_observations), market_return.to_numpy()]
    )
    market_only_result = run_ols_with_newey_west(
        market_only_design_matrix, strategy_return.to_numpy(), lag
    )
    alpha, beta_market = market_only_result["coefficients"]
    t_alpha, t_beta_market = market_only_result["t_statistics"]
    p_alpha, p_beta_market = market_only_result["p_values"]
    print("\n[模型 1] 單因子 (僅市場): exp_002 淨報酬 = alpha + beta_市場 * 買入持有報酬")
    print(f"  alpha (年化)  : {_annualize_daily_alpha(alpha):+7.2%}   (t={t_alpha:+.2f}, p={p_alpha:.3f})")
    print(f"  beta_市場      : {beta_market:+7.3f}   (t={t_beta_market:+.2f}, p={p_beta_market:.3f})")
    print(f"  R²             : {market_only_result['r_squared']:.3f}")

    two_factor_design_matrix = np.column_stack(
        [np.ones(number_of_observations), market_return.to_numpy(), momentum_return.to_numpy()]
    )
    two_factor_result = run_ols_with_newey_west(
        two_factor_design_matrix, strategy_return.to_numpy(), lag
    )
    alpha_2f, beta_market_2f, beta_momentum_2f = two_factor_result["coefficients"]
    t_alpha_2f, t_beta_market_2f, t_beta_momentum_2f = two_factor_result["t_statistics"]
    p_alpha_2f, p_beta_market_2f, p_beta_momentum_2f = two_factor_result["p_values"]
    print("\n[模型 2] 兩因子 (市場 + 動能): exp_002 淨報酬 = alpha + beta_市場*買入持有報酬 + beta_動能*動能因子報酬")
    print(f"  alpha (年化)   : {_annualize_daily_alpha(alpha_2f):+7.2%}   (t={t_alpha_2f:+.2f}, p={p_alpha_2f:.3f})")
    print(f"  beta_市場      : {beta_market_2f:+7.3f}   (t={t_beta_market_2f:+.2f}, p={p_beta_market_2f:.3f})")
    print(f"  beta_動能      : {beta_momentum_2f:+7.3f}   (t={t_beta_momentum_2f:+.2f}, p={p_beta_momentum_2f:.3f})")
    print(f"  R²             : {two_factor_result['r_squared']:.3f}")

    print(
        f"\n  alpha 變化: 加入動能因子前為 {_annualize_daily_alpha(alpha):+.2%} (p={p_alpha:.3f}), "
        f"加入動能因子後變為 {_annualize_daily_alpha(alpha_2f):+.2%} (p={p_alpha_2f:.3f})"
    )


def main() -> None:
    ohlcv_dataframe = load_btc_ohlcv_dataframe()
    strategy = TrendFollowingStrategy(**STRATEGY_PARAMETERS)
    engine = BacktestEngine(**ENGINE_PARAMETERS)

    # 全樣本連續回測 (非官方 70/30 切分) : 統計檢定力最大化, 且無切分邊界的指標冷啟動失真
    # 這不是重新調參 (策略參數已凍結, 照抄 config.py) , 只是為了這次診斷性迴歸盡量拿到最多觀測值
    full_sample_result = engine.run(ohlcv_dataframe, strategy)
    market_return_full = compute_market_factor_return(ohlcv_dataframe)
    momentum_return_full = compute_momentum_factor_return(ohlcv_dataframe, market_return_full)
    _print_regression_report(
        "exp_002 因子迴歸: 全樣本連續回測 (2017-08~2026-07)",
        full_sample_result.daily_return_percentage,
        market_return_full,
        momentum_return_full,
    )

    # 官方樣本外 (OOS) 穩健性檢查: 對齊 run_with_split 的官方切分, 呼應本專案 OOS 數字才算數的慣例
    # 動能因子仍用全樣本算好再切片, 讓 365 天落後窗口的暖身期吃樣本內, 不吃掉樣本外的天數
    _, out_of_sample_dataframe = split_in_sample_out_of_sample(ohlcv_dataframe, IN_SAMPLE_RATIO)
    _, out_of_sample_result = engine.run_with_split(ohlcv_dataframe, strategy, IN_SAMPLE_RATIO)
    market_return_oos = market_return_full.loc[out_of_sample_dataframe.index].reset_index(drop=True)
    momentum_return_oos = momentum_return_full.loc[out_of_sample_dataframe.index].reset_index(
        drop=True
    )
    _print_regression_report(
        "exp_002 因子迴歸: 官方樣本外 (OOS) 穩健性檢查",
        out_of_sample_result.daily_return_percentage,
        market_return_oos,
        momentum_return_oos,
    )
    print()


if __name__ == "__main__":
    main()
