"""
exp_004 EMA + ADX + ATR 移動止損 — 承接 exp_002 (best-so-far), 維持快速進場, 出場改由 3×ATR 移動止損接管
假設: exp_003 證明放慢慢線會連進場一起拖慢; 移動止損解耦進出場(快進場 + 只在真反轉才出), 抱住趨勢更久拉高 CAGR, 把 Sharpe 過 1.0
策略參數與 exp_002 完全相同; 唯一改動是引擎啟用 trailing_stop_atr_multiplier=3.0 (取代 EMA 出場)
執行: 直接 python config.py (資料夾名字自動當實驗名), 或 python ../run_experiment.py exp_004_trailing_stop
"""

# 數據: 02_data/cache 下的檔名(由 02_data/fetchers 抓取)
DATASET = "btc_usdt_1d.csv"

# 策略: 對應 run_experiment.py 的 STRATEGY_REGISTRY
STRATEGY = "trend_following"
# 策略參數: 與 exp_002 完全相同 (fast 12, slow 26, adx 25); 進場邏輯不動, 改動只在引擎的出場
STRATEGY_PARAMS = {
    "fast_span": 12,
    "slow_span": 26,
    "adx_period": 14,
    "adx_threshold": 25.0,
}

# 引擎參數: 同 exp_002; 唯一新增 trailing_stop_atr_multiplier=3.0 啟用移動止損出場(取代 EMA 出場)
# 註: atr_stop_multiplier=2.0 只管倉位大小, 與出場用的移動止損 3.0 相互獨立
ENGINE_PARAMS = {
    "initial_capital": 10_000.0,
    "risk_per_trade_percentage": 0.01,
    "atr_stop_multiplier": 2.0,
    "atr_period": 14,
    "fee_rate": 0.001,
    "slippage_rate": 0.0005,
    "max_position_fraction": 1.0,
    "trading_days_per_year": 365,
    "trailing_stop_atr_multiplier": 3.0,
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
