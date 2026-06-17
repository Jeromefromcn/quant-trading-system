# 量化交易系統行動路線圖

> 從業務學習到 Paper Trading, 再到實盤的完整工程指南 
> 加密貨幣 + 美股 · 趨勢跟蹤策略 · Monorepo · Git First · 2026

---

## 開始之前: 待確認事項

> 這 4 點影響後續所有時間估算和工具選型, 先對自己確認清楚

- [x] **01 Python 熟練程度**: 如果主要背景是 Java 或 Go, 需要額外花 1-2 週熟悉 pandas 向量化數據操作(思維方式切換, 不只是語法)
- [x] **02 每週可投入時間**: 本路線圖基於 5-10 小時 / 週. 如果每週只有 3-4 小時, 所有時間線乘以 1.5 倍
- [x] **03 帳戶狀態**: 確認 Binance Testnet(testnet.binance.vision) 和 Alpaca Paper Trading 帳戶已建立並拿到 API Key
- [x] **04 Paper Trading 模擬資金規模**: 設定為計劃實際投入的金額(例如 $10,000 USD) , 從一開始用真實規模計算倉位

---

## Pre-Phase 0: Pandas 向量化思維

> ⏱ 1-2 週 · 8 個練習腳本 · 位於 `01_learning/01_pandas/` 
> 核心原則: 零 for loop, 零 if-else(信號邏輯除外) , 用向量化思維操作數據

- [x] `01_data_structures.py`: Series / DataFrame 基礎, 對應 Go 的 `[]float64` 與 `[]map[string]float64`
- [x] `02_shift_rolling.py`: 位移與滾動操作 — `shift` / `rolling` / `expanding` / `ewm` / `diff`, 量化最常用
- [x] `03_boolean_indexing.py`: 篩選與布林索引, pandas 的 if-else 替代方案
- [x] `04_groupby_merge_resample.py`: 分組, 合併, 重採樣 — 多數據源整合的核心工具
- [x] `05_apply.py`: `apply` 的正確使用場景 — 能向量化就向量化, `apply` 是最後手段
- [x] `06_quant_examples.py`: 量化場景示例 — 收益率, 風險指標, 技術指標計算, 信號生成
- [x] `07_common_patterns.py`: 常用模式速查 + 常見陷阱, 遇到問題先查這裡
- [x] `08_exercises.py`: 自我驗收三道題 — 不超過指定行數, 零 for loop, 零 if-else

### Pre-Phase 0 完成標準

- [x] `08_exercises.py` 三道題全部通過, 且符合行數限制
- [x] 能不查文檔寫出 `shift(1)` 計算昨日收盤, `rolling(20).mean()` 計算 20 日均線, `resample('W').agg({'close': 'last'})` 重採樣
- [x] 理解為什麼 `apply(lambda row: ...)` 比向量化慢 10-100 倍

---

## Phase 0: 基礎設施建設

> ⏱ 1-2 天 · 只做一次 · 之後每一天都在這個地基上工作

### 任務(按順序執行)

- [x] **1. 建立 GitHub Private Repo**: 名字建議 `quant-trading`, 設為 Private, 初始化時勾選 Add README
- [x] **2. 建立 Python 環境**: 用 `pyenv + virtualenv` 或 `conda`, Python 3.11+, 安裝 `pandas numpy matplotlib requests python-dotenv jupyter`
- [x] **3. 生成倉庫目錄結構**: 讓 Claude Code 生成 bash 腳本, 創建所有目錄, 每個目錄放空 README.md, 生成 `.gitignore` 和 `.env.example`
- [x] **4a. 申請 Binance Testnet API Key**: 訪問 `testnet.binance.vision`, 無需 KYC, 5 分鐘完成, 填入本地 `.env`
- [x] **4b. 申請 Alpaca Paper Trading API Key**: 訪問 `alpaca.markets`, 免費帳戶, 拿到 Paper API Key, 填入本地 `.env`
- [x] **4c. 確認 `.env` 已在 `.gitignore` 第一行**, 且 `.env.example` 只放佔位符
- [x] **5. 第一個 Git Commit**: `git commit -m "init: project structure, gitignore, env template"` 並推送到 GitHub

### Phase 0 完成標準

- [x] Repo 建立完成, 目錄結構齊全, 推送到 GitHub
- [x] `.env` 已在 `.gitignore` 中, 且已填好 API Key
- [x] 用測試腳本確認 Binance Testnet API 可以成功調用
- [x] 用測試腳本確認 Alpaca Paper API 可以成功調用
- [x] 第一個 commit 已推送

---

## Phase 1: 業務學習

> ⏱ 3-4 週 · 10 個概念腳本 · 每週 2-3 個 
> 核心原則: 每個概念, 用代碼驗證理解, 不是用文字記憶

### 週 1: K 線, 均線, 波動率

每個腳本完成後, 需走完 5 步工作流(見下方) :

- [ ] `01_ohlcv_basics.py`: K 線是什麼, 從 Binance 拿到第一份真實數據並存本地
- [ ] `02_ema_sma.py`: 均線計算, 可視化, 業務含義
- [ ] `03_atr.py`: 波動率測量, 止損的基礎

**週 1 能力驗證**: 能理解 K 線含義, 畫出均線, 計算波動率

### 週 2: 策略評估, 倉位管理

- [ ] `04_sharpe_drawdown.py`: 策略評估的兩個核心指標
- [ ] `05_position_sizing.py`: 固定風險倉位法 — 每筆虧多少

**週 2 能力驗證**: 能計算 Sharpe 和最大回撤; 能用 ATR 計算每筆應買多少以控制風險

### 週 3: 第一個完整回測

- [ ] `06_simple_backtest.py`: 第一個完整回測, 端到端跑通
- [ ] `07_backtest_metrics.py`: 計算所有績效指標
- [ ] **手動核對至少 10 筆交易**的計算是否正確

**週 3 能力驗證**: 能跑出第一個完整回測並手動核對

### 週 4: 回測陷阱識別

- [ ] `08_overfitting.py`: 過擬合是什麼, 怎麼識別
- [ ] `09_lookahead_bias.py`: 前視偏差演示與預防(重點: 信號用前一天收盤價, 不是當天)
- [ ] `10_train_test_split.py`: 樣本內外劃分, walk-forward 驗證

**週 4 能力驗證**: 能識別回測是否有過擬合或前視偏差, 能正確劃分樣本內外數據

### 每個腳本的 5 步工作流

- [ ] 給 Claude Code 寫 Prompt, 生成最小可運行腳本(每行加業務含義注釋, 帶可視化, 不超過 60 行)
- [ ] 跑起來, 判斷輸出是否在直覺上合理(例: EMA 比 SMA 對近期價格更敏感? ATR 在大波動時更高? )
- [ ] 主動改動至少一項: ① 改參數先預測再驗證 / ② 注釋掉一行看報錯 / ③ 換資產(ETH 或 SPY)
- [ ] 自我測試三問: ① 業務上代表什麼? ② 局限性和失效條件? ③ 用作交易信號最大風險是什麼?
- [ ] Commit, 格式: `learn: [概念] - [一行關鍵洞察]`

### Phase 1 完成標準

- [ ] 能回答: 勝率 35%, 平均盈利是平均虧損 3 倍, 長期期望值是正還是負? (說出計算過程)
- [ ] 能回答: 回測 Sharpe 2.5 但只測了 6 個月, 這個結果可信嗎? 為什麼?
- [ ] 能回答: 為什麼止損要用 ATR 倍數, 而不是固定的 5%?

---

## Phase 2: 策略研究

> ⏱ 4-8 週 · 目標 20+ 次有記錄的實驗 
> 核心原則: 系統性地提出假設, 驗證假設, 記錄結論

### 第一週: 搭建回測引擎(`03_research/backtest/engine.py`)

- [ ] **手續費模擬**: Binance Taker 0.1%, Alpaca 加 0.03% 估算 bid-ask spread
- [ ] **滑點模擬**: 每筆交易加 0.05% 保守估算
- [ ] **固定風險倉位**: 每筆風險 = 賬戶 × 1-2%, 止損距離 = 2×ATR, 計算買入數量
- [ ] **樣本劃分**: 前 70% 樣本內(調參) , 後 30% 樣本外(驗證) , 樣本外數字才算數
- [ ] **標準化輸出**: JSON 格式績效報告 + 淨值曲線圖
- [ ] **手動核對**: 新引擎完成後至少核對 10 筆交易的計算正確性

### 每次實驗的 5 步工作流

- [ ] 在 `STRATEGY_LOG.md` 先寫假設, 再動代碼("加入 ADX>25 能減少震盪市假信號" 才是假設)
- [ ] 建立 `experiments/exp_XXX/` 文件夾, 複製上一個實驗的 `config.py` 修改參數
- [ ] 跑回測, 保存 `results.json`(同時跑樣本內和樣本外)
- [ ] 寫 `notes.md`, 更新 `STRATEGY_LOG.md`(必須寫結論, 失敗實驗同樣有價值)
- [ ] Commit, 格式: `research: exp_XXX [策略名] - OOS Sharpe=X.X MaxDD=-XX%`

### 研究推進序列

**第 1 輪: 建立基準**
- [ ] EMA 雙均線基準版, 同時測 BTC/USDT
- [ ] EMA 雙均線基準版, 同時測 ETH/USDT
- [ ] EMA 雙均線基準版, 同時測 SPY
- [ ] EMA 雙均線基準版, 同時測 QQQ
- [ ] 記錄並對比不同市場的績效差異, 建立基準

**第 2 輪: 改善信號質量**
- [ ] ADX > 25 過濾條件(減少震盪市假信號)
- [ ] 成交量確認(放量才入場)
- [ ] ATR 止損倍數 1.5x 對比測試
- [ ] ATR 止損倍數 2.0x 對比測試
- [ ] ATR 止損倍數 2.5x 對比測試

**第 3 輪: 優化執行頻率**
- [ ] 日線 vs 4 小時線對比(加密貨幣)
- [ ] 多時間框架確認(高時間框架趨勢 + 低時間框架入場)
- [ ] 美股最優執行頻率確認

**第 4 輪: 組合與風控**
- [ ] 加密 + 美股同時持倉的相關性分析
- [ ] 熔斷邏輯測試(兩個市場同時回撤時的真實風險)
- [ ] 組合策略整體績效評估

### Phase 2 完成標準

- [ ] `STRATEGY_LOG.md` 有 **20+ 條**實驗記錄, 每條都有假設和結論
- [ ] 找到至少一個策略: **樣本外 Sharpe > 1.0, 最大回撤 < 20%**
- [ ] 該策略在包含牛市的數據區間上成立
- [ ] 該策略在包含熊市 / 震盪市的數據區間上成立
- [ ] 能用自己的話解釋: 這個策略為什麼有效, 以及在什麼環境下會失效

---

## Phase 3: Paper Trading

> ⏱ 6-8 週 · 系統完全自動化運行 
> 目標: 發現所有回測看不見的工程問題(API 斷線, 數據延遲, 訂單被拒, 維護窗口)

### 搭建 Agent 系統(`04_paper_trading/agents/`)

- [ ] `data_agent.py`: WebSocket 實時數據拉取 → 標準化 OHLCV DataFrame
- [ ] `signal_agent.py`: 在最新數據上運行策略 → SignalEvent(方向, 強度, 標的)
- [ ] `risk_agent.py`: 風控審核, 硬性規則, 不可繞過 → OrderEvent 或 RejectionEvent
- [ ] `execution_agent.py`: 執行訂單, 記錄結果 → FillEvent 或 FailEvent + 報警

### 風控 Agent 硬性規則實現

- [ ] 單筆最大虧損: 賬戶的 1.5%, 超過直接拒絕
- [ ] 每日最大虧損熔斷: 當日累計虧損 > 4% → 停止當日所有交易, 發 Telegram 報警
- [ ] 最大同時持倉數: 加密貨幣 3 個, 美股 5 個
- [ ] 相關性限制: 新倉與現有持倉相關係數 > 0.8 時拒絕開新倉
- [ ] 數據異常保護: 數據超過 15 分鐘未更新 → 暫停信號生成, 發報警

### 調度與通知

- [ ] `scheduler.py`: 加密貨幣每 4 小時一次(00:00 / 04:00 / 08:00 / 12:00 / 16:00 / 20:00 UTC)
- [ ] `scheduler.py`: 美股每個交易日一次(美東 16:30 收盤後計算信號, 次日開盤前 30 分鐘掛限價單)
- [ ] `monitor.py`: 每日自動生成報告並發送 Telegram(含信號, 執行結果, 持倉, 帳戶摘要, 系統健康)
- [ ] 配置 Telegram Bot Token 和 Chat ID(`.env` 中, 不入 Git)

### 風控規則驗證

- [ ] 單筆最大虧損規則在真實信號下觸發過至少一次, 確認生效
- [ ] 每日熔斷規則在真實信號下觸發過至少一次, 確認生效
- [ ] 持倉數量限制規則確認生效
- [ ] 相關性限制規則確認生效
- [ ] 數據異常保護規則確認生效

### Phase 3 完成標準

- [ ] 連續 **6 週**無重大 Bug(輕微故障可自動恢復)
- [ ] 每日報告連續 6 週正常發送, 無缺漏
- [ ] Paper Trading 績效與回測預期偏差 **< 30%**
- [ ] 所有風控規則在真實信號下至少觸發過一次, 確認規則真的在生效

---

## Phase 4: 實盤交易

> ⏱ Phase 3 完成後才討論 · `05_live/` 現在只有一個 README, 不動任何代碼

> **Phase 3 完成標準 100% 達到之前, `05_live/` 目錄不動任何代碼. **

技術上從 Paper 切換到 Live 只需要一件事: 把 API 端點從 Testnet/Paper 換成正式環境, 代碼邏輯不需要改.

### 進入實盤的前置條件

- [ ] Phase 3 所有完成標準達到
- [ ] Paper Trading 績效與回測偏差 < 30%
- [ ] 第一個月實盤資金為計劃規模的 **20%**(試跑期)
- [ ] 所有風控參數收緊 50%(例: 單筆風險從 1.5% 降到 0.75%)
- [ ] Paper Trading 系統繼續並行運行至少 1 個月(對比驗證)
- [ ] 已了解香港對加密貨幣交易的稅務立場(HK 無資本利得稅, 但加密貨幣有特殊規定)

---

## 預計完整時間線

| 階段 | 時長 | 備注 |
|------|------|------|
| Phase 0 | 1-2 天 | 環境建設, 只做一次 |
| Phase 1 | 3-4 週 | 業務學習 |
| Phase 2 | 4-8 週 | 策略研究 |
| Phase 3 | 6-8 週 | Paper Trading |
| **總計** | **4-6 個月** | 基於 5-10 小時 / 週 |

---

> 先把 Phase 0 建好, 其他的邊做邊看. 每一天的工作都有 Git 記錄, 永遠不會白費.
