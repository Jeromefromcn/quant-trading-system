"""
exp_006 跨市場驗證: 凍結的 exp_002 (best-so-far) 原封不動搬到 ETH/USDT, 檢驗優勢能否泛化
策略與引擎參數與 exp_002 逐項相同, 只換數據為 ETH; 不得為 ETH 調任何參數 (調了就把這個乾淨市場燒成驗證集)
這是跨市場泛化測試 (exp_006-008 之一, 對應 ROADMAP Round 1 跨市場基準), 一次跑完, 結果照單全收
執行: 直接 python config.py (資料夾名字自動當實驗名), 或 python ../run_experiment.py exp_006_eth
"""

# 數據: ETH/USDT 日線 (至今零實驗的乾淨市場, 加密貨幣同 BTC 設定)
DATASET = "eth_usdt_1d.csv"

# 策略: 對應 run_experiment.py 的 STRATEGY_REGISTRY
STRATEGY = "trend_following"
# 策略參數: 與 exp_002 完全相同, 一字不改 (fast 12, slow 26, adx 25)
STRATEGY_PARAMS = {
    "fast_span": 12,
    "slow_span": 26,
    "adx_period": 14,
    "adx_threshold": 25.0,
}

# 引擎參數: 與 exp_002 逐項相同 (ETH 為加密貨幣, 年化用 365, Binance 費率適用)
ENGINE_PARAMS = {
    "initial_capital": 10_000.0,
    "risk_per_trade_percentage": 0.01,
    "atr_stop_multiplier": 2.0,
    "atr_period": 14,
    "fee_rate": 0.001,
    "slippage_rate": 0.0005,
    "max_position_fraction": 1.0,
    "trading_days_per_year": 365,
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
