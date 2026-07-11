"""
exp_002 EMA 雙均線 + ADX 趨勢過濾: 相對 exp_001 只改一個變數, adx_threshold 由 0 改為 25
假設: 只在趨勢明確 (ADX > 25) 時進場, 濾掉盤整市假交叉, 把樣本外 Sharpe 推過 1.0
其餘參數 (數據, EMA 12/26, 引擎, 70/30 分割) 全部與 exp_001 相同, 以便乾淨歸因
執行: 直接 python config.py (資料夾名字自動當實驗名), 或 python ../run_experiment.py exp_002_ema_adx
"""

# 數據: 02_data/cache 下的檔名(由 02_data/fetchers 抓取)
DATASET = "btc_usdt_1d.csv"

# 策略: 對應 run_experiment.py 的 STRATEGY_REGISTRY
STRATEGY = "trend_following"
# 策略參數: EMA 快 12 / 慢 26 與 exp_001 相同; 唯一改動 adx_threshold=25 (ADX>25 才算趨勢明確, 業界慣例)
STRATEGY_PARAMS = {
    "fast_span": 12,
    "slow_span": 26,
    "adx_period": 14,
    "adx_threshold": 25.0,
}

# 引擎參數: 帳戶 $100,000, 每筆風險 1%, 止損 ×ATR, Binance Taker 0.1% + 滑點 0.05%, 加密貨幣年化用 365
# initial_capital 於 2026-07-11 由 $10,000 調整為 $100,000, 對齊 Alpaca Paper Trading 與 Binance
# Testnet 兩邊真實帳戶規模, 讓 04_paper_trading 的名目金額上限與真實淨值同量級, 不再系統性擋下
# 正常大小的開倉. 這個調整只影響 04_paper_trading 的風控上限計算, 不影響本實驗已記錄的 Sharpe /
# CAGR / 最大回撤等績效指標(皆為百分比報酬, 與起始資金絕對值無關), 見 results.json 與 notes.md
# 保留的原始 $10,000 版本記錄
ENGINE_PARAMS = {
    "initial_capital": 100_000.0,
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
