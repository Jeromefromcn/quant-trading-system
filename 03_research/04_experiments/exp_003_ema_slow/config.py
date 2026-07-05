"""
exp_003 EMA 慢線延長 — 承接 exp_002 (best-so-far, adx=25), 只改一個變數: slow_span 26 → 50
假設: 慢線更長使進出場更遲鈍, 趨勢單較不被短期回彈洗出場, 騎更長趨勢段以提高 CAGR, 把 Sharpe 推向 1.0
其餘 (數據, fast_span=12, adx_threshold=25, 引擎, 70/30 分割) 全部與 exp_002 相同, 以便乾淨歸因
執行: 直接 python config.py (資料夾名字自動當實驗名), 或 python ../run_experiment.py exp_003_ema_slow
"""

# 數據: 02_data/cache 下的檔名(由 02_data/fetchers 抓取)
DATASET = "btc_usdt_1d.csv"

# 策略: 對應 run_experiment.py 的 STRATEGY_REGISTRY
STRATEGY = "trend_following"
# 策略參數: 承接 exp_002 (fast 12, adx 25); 唯一改動 slow_span 26 → 50 (慢線延長, 讓趨勢單跑更久)
STRATEGY_PARAMS = {
    "fast_span": 12,
    "slow_span": 50,
    "adx_period": 14,
    "adx_threshold": 25.0,
}

# 引擎參數: 帳戶 $10,000, 每筆風險 1%, 止損 ×ATR, Binance Taker 0.1% + 滑點 0.05%, 加密貨幣年化用 365
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
