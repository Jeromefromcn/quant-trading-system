"""
exp_001 EMA 雙均線基準版 — Round 1 建立基準的第一個實驗, 測 BTC/USDT 日線
只放參數, 不放邏輯; 下一個實驗複製本檔改參數即可. 執行: python ../run_experiment.py exp_001_ema_baseline
"""

# 數據: 02_data/cache 下的檔名(由 02_data/fetchers 抓取)
DATASET = "btc_usdt_1d.csv"

# 策略: 對應 run_experiment.py 的 STRATEGY_REGISTRY
STRATEGY = "trend_following"
# 策略參數: EMA 快線 12 日, 慢線 26 日, adx_threshold=0 代表純均線交叉不做趨勢過濾(基準版)
STRATEGY_PARAMS = {
    "fast_span": 12,
    "slow_span": 26,
    "adx_period": 14,
    "adx_threshold": 0.0,
}

# 引擎參數: 帳戶 $10,000, 每筆風險 1%, 止損 2×ATR, Binance Taker 0.1% + 滑點 0.05%, 加密貨幣年化用 365
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
