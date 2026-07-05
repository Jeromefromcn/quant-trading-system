"""
exp_005 緊移動止損 (1.5×ATR) — 測「贏錢就跑」: 與 exp_004 相同, 只把移動止損倍數 3.0 → 1.5
假設: exp_003/004 證明「抱久」有害, 反方向「早點跑、少回吐」或許有利, 讓小回落就出場, 拉高 Sharpe
與 exp_002 相比只多一個緊移動止損; 與 exp_004 相比只差止損倍數 (3.0→1.5), 兩面都是乾淨單變數對照
警告: 早出場會砍掉趨勢的大贏家, 違背趨勢跟蹤核心邏輯, 結果未知; 且此為 BTC 樣本外第 5 次使用
執行: 直接 python config.py (資料夾名字自動當實驗名), 或 python ../run_experiment.py exp_005_tight_trailing
"""

# 數據: 02_data/cache 下的檔名(由 02_data/fetchers 抓取)
DATASET = "btc_usdt_1d.csv"

# 策略: 對應 run_experiment.py 的 STRATEGY_REGISTRY
STRATEGY = "trend_following"
# 策略參數: 與 exp_002/004 完全相同 (fast 12, slow 26, adx 25); 進場邏輯不動
STRATEGY_PARAMS = {
    "fast_span": 12,
    "slow_span": 26,
    "adx_period": 14,
    "adx_threshold": 25.0,
}

# 引擎參數: 同 exp_004; 唯一改動 trailing_stop_atr_multiplier 3.0 → 1.5 (更早出場, 少回吐 = 贏錢就跑)
ENGINE_PARAMS = {
    "initial_capital": 10_000.0,
    "risk_per_trade_percentage": 0.01,
    "atr_stop_multiplier": 2.0,
    "atr_period": 14,
    "fee_rate": 0.001,
    "slippage_rate": 0.0005,
    "max_position_fraction": 1.0,
    "trading_days_per_year": 365,
    "trailing_stop_atr_multiplier": 1.5,
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
