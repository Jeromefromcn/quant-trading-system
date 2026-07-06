# Phase 3 紙上交易 (paper trading) 第一切片 (slice) 設計文件

日期: 2026-07-06
狀態: 已核准 (approved) , 待寫實作計劃 (implementation plan)

## 背景 (background)

exp_002 (EMA 雙均線 + ADX 過濾) 已凍結, 跨 BTC / ETH / SPY / QQQ 四市場驗證皆為正 Sharpe, 且因子迴歸 (factor regression) 分析顯示: 在真正的樣本外 (out-of-sample, OOS) 窗口中, 統計上找不到顯著獨立於市場與動能因子之外的 alpha (詳見 `project_manage/STRATEGY_LOG.md` 2026-07-06 條目). 歷史數據已榨不出更多乾淨資訊, 依專案方法論 ("數據用完怎麼辦" 三守則) , 這是轉往 Phase 3 紙上交易向前驗證的訊號, 而非「找到 alpha」的慶祝訊號.

Phase 3 目標 (依 `project_manage/ROADMAP.md`) 是用 4-agent 系統 (data / signal / risk / execution) 自動化跑 exp_002, 發現回測看不到的工程問題 (API 斷線, 訂單被拒, 數據延遲等). 完整範圍涵蓋 6 個子系統 (四個 agent 加上排程器 scheduler 與監控 monitor) , 彼此構成一條 pipeline, 一次全部設計規格過大. 本文件只涵蓋**第一個切片 (Slice 1) **: 一條最小可跑通的端到端路徑, 用來驗證 pipeline 本身能否接上, 而不是把任一 agent 一次做到完整穩健. 其餘切片 (股票, 完整風控規則, 排程器, 監控) 在此切片證明可行後, 各自另開規格.

## 目標與範圍 (goal and scope)

**目標**: 用凍結不變的 exp_002 策略, 對真實外部系統 (Binance Testnet) 跑通一次完整的 data → signal → risk → execution pipeline.

**本切片範圍內**:
- 僅 BTC/USDT, 透過 Binance Testnet (`testnet.binance.vision`)
- 手動觸發 (跑一次腳本, 非排程自動化)
- 最小風控: 僅倉位大小上限檢查
- 真實下單 (打真正的 Testnet 下單端點, 非模擬) , 因為 Phase 3 的目的正是暴露真實 API 問題

**明確排除, 留給後續切片**:
- Alpaca 美股 (Slice 2)
- 完整風控規則: 每日熔斷, 相關性限制, 最大同時持倉數, 數據延遲保護 (Slice 3)
- 排程器自動化 (Slice 4)
- 監控與 Telegram 每日報告 (Slice 5)
- WebSocket 即時串流: exp_002 策略以日線決策, 依 ROADMAP 加密貨幣排程「每 4 小時一次」的頻率, 不需要次秒級數據. 沿用現有 `binance_fetcher.py` 的 REST 輪詢 (polling) 風格即可, WebSocket 留給未來真的需要盤中即時數據的策略再加

## 元件 (components)

新增檔案:

- `04_paper_trading/events.py` — 型別化事件 (typed events) : `SignalEvent`, `OrderEvent`, `RejectionEvent`, `FillEvent`, `FailEvent` (dataclass)
- `04_paper_trading/agents/data_agent.py` — 拉取最新 K 線
- `04_paper_trading/agents/signal_agent.py` — 跑凍結策略, 決定目標倉位
- `04_paper_trading/agents/risk_agent.py` — 比對目標倉位與當前倉位, 套用倉位上限檢查
- `04_paper_trading/agents/execution_agent.py` — 下真實 Testnet 訂單並確認成交
- `04_paper_trading/binance_testnet_client.py` — 簽名 (signed) REST 客戶端 (帳戶資訊, 下單, 查詢訂單狀態)
- `04_paper_trading/run_once.py` — 串接 4 個 agent 的執行腳本, 附執行紀錄
- `04_paper_trading/logs/run_log.jsonl` — 逐次執行紀錄, gitignore 排除

**運行架構**: 循序腳本呼叫, 非事件匯流排 (event bus) / 訊息佇列 (message queue) . 每個 agent 是一般函式, 用型別化事件物件互相傳遞資料, 而非透過佇列發布訂閱. 這在還不知道是否需要獨立行程 (process) 的階段, 用最少機關換到大部分清晰度: 每個 agent 的決策邏輯可獨立單元測試, 未來真的需要拆成獨立行程或排程時, 再演進.

**關鍵重用決策**: `signal_agent` 直接從 `exp_002_ema_adx/config.py` import `STRATEGY_PARAMS` / `ENGINE_PARAMS` (已確認該檔案的執行邏輯包在 `if __name__ == "__main__"` 之後, import 它不會觸發副作用) , 不重複宣告參數字典. 確保紙上交易用的參數永遠與已回測凍結的版本一致, 不會悄悄漂移.

## 資料流 (data flow) — 單次執行逐步說明

1. **`data_agent.fetch_latest_candles(symbol, lookback_bars)`**: 從 Binance 公開 K 線端點拉取最近約 60 根 BTC/USDT 日線 (足夠 slow_span=26 + adx_period=14 的暖身期) . 把共用的請求邏輯從既有 `binance_fetcher.py` 抽出重用, 不重寫一份, 讓歷史抓取與即時抓取共用同一段已測試過的程式碼路徑.

2. **`signal_agent.decide(ohlcv_dataframe)`**: 用凍結參數 `TrendFollowingStrategy(**STRATEGY_PARAMS)` 跑這個窗口, 取最後一列的目標倉位 (0 或 1) → `SignalEvent(symbol, target_position, as_of_timestamp, latest_close_price)`.

3. **`risk_agent.review(signal_event, account_state, risk_limits)`**: 透過 `binance_testnet_client` 查詢當前 BTC / USDT 餘額, 換算成 `current_position` (0 或 1; BTC 餘額市值低於 10 USDT 視為粉塵 (dust) , 算作空手) , 與 `target_position` 比較, 三種結果 (不是兩種) :
   - **目標 == 當前** → `None` (無需動作, 記錄為安靜的無操作, 不算 rejection)
   - **目標 != 當前, 且在風控上限內** → `OrderEvent`, 方向與數量依情境決定 (兩個方向計算方式不同, 不可混用) :
     - **空手 → 多單 (買進) **: 數量透過引擎既有的 `compute_position_fraction` 計算 (依 1% 風險 / 2×ATR 止損反推) , 讓紙上交易的進場大小與回測時完全一致
     - **多單 → 空手 (賣出) **: 數量固定為「當前實際持有的全部 BTC 餘額」, 直接全部平倉, 不重新跑風險計算 (`compute_position_fraction` 是進場用的風險換算, 不適用於平倉數量)
     - **風控上限檢查本身**: 買進方向額外檢查算出的名目金額 (notional) 不超過帳戶規模 (`ENGINE_PARAMS["initial_capital"]`) 乘上 `max_position_fraction`, 作為 `compute_position_fraction` 內部裁剪之外的第二層防呆 (defense-in-depth) , 防止帳戶規模設定或計算異常時仍下出過大訂單; 賣出方向天然受限於實際持倉, 不需要另外設檢查
   - **目標 != 當前, 但超過風控上限** → `RejectionEvent(reason)` (原本該交易, 但被風控擋下 — 這個區分之後對監控很重要, 才能分清「今天沒信號」與「風控觸發」)

4. **`execution_agent.execute(order_event)`**: 透過 `binance_testnet_client` 下真實市價單, 輪詢訂單狀態直到成交或明確失敗 → `FillEvent(quantity, average_price, order_id)` 或 `FailEvent(reason, raw_exchange_response)`.

5. **`run_once.py`**: 把每一步的結果 (含無操作情形) 記錄成一行 JSON 寫入 `logs/run_log.jsonl`, 並印出人類可讀摘要. 因為每次都向真實交易所狀態核對而非信任本地記憶, 重複執行是安全的 (見下方錯誤處理的冪等性 (idempotency) 討論) .

## 錯誤處理 (error handling)

- **數據抓取失敗或逾時** → `run_once.py` 攔截, 記錄失敗, 以非零狀態碼結束. 不執行部分 pipeline — 寧可整段失敗, 也不用不完整數據猜測.
- **K 線數量不足暖身期** (API 偶發只回傳不足的根數) → `signal_agent` 應拒絕產生信號, 而非在 NaN 充斥的指標窗口上硬算; 這是明確報錯, 不是悄悄退回空手.
- **成交狀態不明確** (下單後、確認前斷線) → `execution_agent` 一律用客戶端訂單 ID (client order ID) 重新查詢訂單狀態, 不盲目重試 — 盲目重試在「可能已經下單」的狀態下重試, 有重複下單風險, 這正是 Phase 3 要暴露的工程問題類型. 真的查不出狀態時, 記錄明確的「狀態不明, 需人工核對」, 不用猜測掩蓋.
- **交易所端拒絕** (Binance Testnet 有真實的 MIN_NOTIONAL / LOT_SIZE 等過濾規則) → `execution_agent` 把交易所給的真實拒絕原因原封記入 `FailEvent`, 不用通用錯誤訊息蓋過去.
- **冪等性 (idempotency) **: 因為目前是手動觸發 (非排程) , 連續跑兩次 `run_once.py` 必須安全. 這從第 3 步「一律查詢真實帳戶狀態而非信任本地狀態」自然導出: 第二次執行會看到目標 == 當前, 無操作.

## 測試與檔案結構 (testing and file layout)

**純決策邏輯** — `signal_agent` 的「取最後一列」、`risk_agent` 的比對與上限檢查、透過既有 `compute_position_fraction` 計算的倉位大小 — 用合成 (synthetic) 的 DataFrame / 帳戶狀態寫單元測試, 不打真實網路請求, 依本專案慣例以 TDD (test-driven development, 測試驅動開發) 方式撰寫 (`tests/test_paper_trading_signal_agent.py`, `tests/test_paper_trading_risk_agent.py`, 沿用既有 `tests/test_*.py` 命名慣例) .

**I/O 邊界** — `binance_testnet_client` 的簽名 HTTP 呼叫與完整 `run_once.py` pipeline — 刻意不在自動化測試中模擬 (mock) . 作為本切片收尾的一部分, 會實際對真正的 Binance Testnet 跑至少一次手動執行 (`.env` 中的憑證已備妥) , 因為暴露真實 API 行為正是 Phase 3 存在的目的.

**檔案結構**:

```
04_paper_trading/
  events.py
  binance_testnet_client.py
  run_once.py
  agents/
    data_agent.py
    signal_agent.py
    risk_agent.py
    execution_agent.py
  logs/                      # gitignore 排除
    run_log.jsonl
tests/
  test_paper_trading_signal_agent.py
  test_paper_trading_risk_agent.py
```
