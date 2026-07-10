"""
exp_007 跨市場驗證: 凍結的 exp_002 (best-so-far) 搬到美股 SPY, 檢驗優勢能否跨資產類別泛化
策略參數與 exp_002 逐項相同, 只換數據為 SPY; 引擎唯一調整 trading_days_per_year=252 (美股年化正確性修正, 非調參)
費率故意維持 Binance 0.1% (對股票偏保守/高估成本; 若在高估成本下仍成立則證據更強, 也避免調低成本讓股票好看的嫌疑)
不得為 SPY 調任何策略參數 (調了就把這個乾淨市場燒成驗證集). exp_006-008 之一
執行: 直接 python config.py (資料夾名字自動當實驗名), 或 python ../run_experiment.py exp_007_spy
"""

# 數據: SPY 日線 (至今零實驗的乾淨市場, 美股大盤 ETF)
DATASET = "spy_1d.csv"

# 策略: 對應 run_experiment.py 的 STRATEGY_REGISTRY
STRATEGY = "trend_following"
# 策略參數: 與 exp_002 完全相同, 一字不改 (fast 12, slow 26, adx 25)
STRATEGY_PARAMS = {
    "fast_span": 12,
    "slow_span": 26,
    "adx_period": 14,
    "adx_threshold": 25.0,
}

# 引擎參數: 同 exp_002; 唯一改動 trading_days_per_year, 由 365 改為 252 (美股一年約 252 交易日, 純年化正確性修正)
ENGINE_PARAMS = {
    "initial_capital": 10_000.0,
    "risk_per_trade_percentage": 0.01,
    "atr_stop_multiplier": 2.0,
    "atr_period": 14,
    "fee_rate": 0.001,
    "slippage_rate": 0.0005,
    "max_position_fraction": 1.0,
    "trading_days_per_year": 252,
}

# 樣本劃分: 前 70% 樣本內調參, 後 30% 樣本外驗證
IN_SAMPLE_RATIO = 0.7


if __name__ == "__main__":
    # 直接執行本檔即可跑這個實驗; 本檔所在資料夾的名字自動當成實驗名傳入主函數
    import os
    import sys

    _config_directory = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_config_directory))
    from run_experiment import run_and_print_summary

    run_and_print_summary(os.path.basename(_config_directory))
