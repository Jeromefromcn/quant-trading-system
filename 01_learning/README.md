# Phase 1：學習進度

每個概念用代碼驗證理解，不是用文字記憶。

## 概念清單

- [ ] `01_ohlcv_basics.py` — K 線是什麼，拿到第一份真實數據
- [ ] `02_ema_sma.py` — 均線計算、可視化、業務含義
- [ ] `03_atr.py` — 波動率測量，止損的基礎
- [ ] `04_sharpe_drawdown.py` — 策略評估的兩個核心指標
- [ ] `05_position_sizing.py` — 固定風險倉位法：每筆虧多少
- [ ] `06_simple_backtest.py` — 第一個完整回測，端到端跑通
- [ ] `07_backtest_metrics.py` — 計算所有績效指標
- [ ] `08_overfitting.py` — 過擬合是什麼，怎麼識別
- [ ] `09_lookahead_bias.py` — 前視偏差演示與預防
- [ ] `10_train_test_split.py` — 樣本內外劃分：walk-forward 驗證

## Phase 1 完成標準

能回答以下三個問題才進入 Phase 2：

1. 一個策略勝率 35%，平均盈利是平均虧損的 3 倍，長期期望值是正還是負？
2. 回測 Sharpe 2.5，但只測了 6 個月數據，這個結果可信嗎？為什麼？
3. 為什麼止損要用 ATR 倍數，而不是固定的 5%？
