# Phase 3 紙上交易 (paper trading) 第二切片 (slice) 設計文件 : 風控硬性規則與雙標的擴展

日期 : 2026-07-06
狀態 : 已核准 (approved), 待寫實作計劃 (implementation plan)

## 背景 (background)

Slice 1 已完成並跑通一次真實 Binance Testnet 下單 : `data_agent` → `signal_agent` → `risk_agent` → `execution_agent` 這條 pipeline 對 BTC/USDT 單一標的可以接通, 且風控只做了最小的倉位大小上限檢查. 詳見 `docs/superpowers/specs/2026-07-06-phase3-paper-trading-slice1-design.md` 的「已知遺留事項」段落.

依 `project_manage/ROADMAP.md` 的 Phase 3 排序, 4 個 agent 建好之後, 下一段是「風控 (risk control) Agent 硬性規則實現」: 單筆最大虧損, 每日熔斷 (circuit breaker), 最大同時持倉數, 相關性限制, 數據異常保護, 共 5 條規則. 其中「最大同時持倉數」與「相關性限制」兩條規則, 若系統永遠只交易 BTC/USDT 一個標的, 邏輯上不可能真正觸發 (只會有 0 或 1 個倉位, 無「第二個倉位」可比較相關係數或計數). 為了讓這兩條規則在本切片就能被真實信號觸發並驗證 (呼應 ROADMAP 的「風控規則驗證」段落要求), 本切片同時把交易標的從純 BTC/USDT 擴展為 BTC/USDT + ETH/USDT 兩個標的, 沿用同一個 Binance Testnet client 與 `exp_002` 凍結參數 (`exp_006` 已驗證 ETH/USDT 上同一組參數為正 Sharpe, 見 `project_manage/STRATEGY_LOG.md`).

Alpaca 美股整合, 排程器 (scheduler) 自動化, 每日彙總報告仍然是各自獨立的關注點, 不在本切片範圍內, 留給後續切片各自另開規格.

## 目標與範圍 (goal and scope)

**目標** : 在 Slice 1 的 4-agent pipeline 上, 新增 ROADMAP 列出的 5 條風控硬性規則, 並擴展至 BTC/USDT + ETH/USDT 雙標的, 讓「最大同時持倉數」與「相關性限制」有真實的第二標的可以比較, 同時整合真實 Telegram 警報 (非留待監控切片的佔位).

**本切片範圍內** :

- 交易標的由 BTC/USDT 擴展為 `["BTCUSDT", "ETHUSDT"]`, 兩者共用同一 `binance_testnet_client`、同一組 `exp_002` 凍結策略參數與引擎參數 (`ENGINE_PARAMS`)
- 5 條風控硬性規則 :
  1. 單筆最大虧損 : 以「數量 × 停損距離 (`atr_stop_multiplier` × ATR, average true range, 平均真實區間)」估算該筆潛在虧損金額, 超過帳戶淨值 1.5% 直接拒絕. 這與 Slice 1 既有的名目金額 (notional) 上限檢查是不同維度的雙層防呆 (defense-in-depth) : 一個限制潛在虧損, 一個限制部位金額本身, 兩者獨立生效, 互不取代
  2. 每日最大虧損熔斷 : 當日累計虧損 (相對於當日開始時的帳戶淨值) 超過 4%, 停止當日所有交易(該次執行內, 所有標的皆回報 `RejectionEvent`), 並發一次 Telegram 警報
  3. 最大同時持倉數 : 加密貨幣類別上限 3(本切片實際最多只會用到 2, 因為只有 BTC / ETH 兩個標的; 上限值仍照 ROADMAP 設定為 3, 為未來加入第三個加密貨幣標的預留); 美股上限 5(本切片尚無美股標的, 檢查邏輯存在但不會被觸發)
  4. 相關性限制 : 新開倉標的與「現有持倉」(定義見下方資料流第 4 步) 的每日報酬率相關係數 (correlation coefficient) 超過 0.8, 拒絕該筆開倉
  5. 數據異常保護 : 重新解讀 ROADMAP 原文的「15 分鐘」門檻(原文以固定 15 分鐘表述, 對次秒級或分鐘級數據合理, 但 `exp_002` 策略以日線 (daily bar) 決策, 每根 K 線 24 小時才收一次盤, 固定 15 分鐘門檻對日線沒有意義, 幾乎每次檢查都會誤判為過期); 改為以 K 線週期 (bar interval) 為基準的相對門檻, 預設為週期的 1.5 倍(日線即 36 小時) — 抓的是「數據源真的卡住/斷線」, 而不是「日線本來就不是每 15 分鐘更新一次」這個正常現象
- 真實 Telegram 警報整合(`telegram_alerts.py`), 而非留白等監控切片再接
- `.env` / `.env.example` 新增 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID` 佔位

**明確排除, 留給後續切片** :

- Alpaca 美股整合(交易對象、市場開盤時間處理、另一套下單客戶端)
- `scheduler.py` 排程自動化
- `monitor.py` 每日彙總報告(與本切片的即時警報是分開的關注點 : 警報是「有異常立刻通知」, 每日報告是「不論有無異常都定期彙總」)
- WebSocket 即時串流(理由同 Slice 1 : 日線決策不需要次秒級數據)

## 元件 (components)

新增檔案 :

- `04_paper_trading/daily_risk_state.py` — 每日風控狀態的讀寫與重置判斷. 純函式 `should_reset_for_new_day(stored_utc_date, current_utc_date) -> bool`(依 UTC 日期比對, 不同即需重置); I/O 函式 `load_daily_state(file_path) -> dict`、`save_daily_state(file_path, state) -> None`, 存取 `logs/daily_risk_state.json`(格式 : `{"utc_date": "2026-07-06", "equity_at_day_start_usdt": 10000.0}`, 由 gitignore 排除, 與 `logs/run_log.jsonl` 同一層級). 檔案遺失或無法解析時, 視為「尚無基準」, 直接以當前帳戶淨值重置, 不阻擋交易(這份檔案是本地快取, 不是真相來源, 真相來源永遠是交易所當前查詢到的淨值)
- `04_paper_trading/telegram_alerts.py` — `send_alert(message: str) -> None`, 用與 `binance_testnet_client.py` 相同的 `load_dotenv` 手法從 `.env` 讀取 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`, 對 Telegram Bot API 的 `sendMessage` 端點發 HTTP POST. 內部捕捉 `requests.exceptions.RequestException`, 記錄失敗但不往外拋 — 警報發送失敗不能推翻或掩蓋一個已經正確做出的風控決策(例如熔斷已經生效, 不該因為 Telegram 送不出去就讓這次執行以例外中止)

修改檔案 :

- `04_paper_trading/agents/risk_agent.py` — 新增 5 個獨立可測試的純函式, 分別對應 5 條規則; 原本處理單一標的的 `review()` 改為 `review_portfolio(signal_events: list[SignalEvent], current_positions: dict[str, float], account_equity_usdt: float, day_start_equity_usdt: float, price_histories: dict[str, pd.DataFrame], engine_parameters: dict, risk_limits: dict) -> dict[str, OrderEvent | RejectionEvent | None]`, 一次對整批標的做出決策, 內部依序套用 : 全域每日熔斷檢查 (一次) → 逐標的數據異常檢查 → 逐標的目標倉位比對 → 開倉方向的四項檢查(單筆最大虧損、最大同時持倉數、相關性限制、Slice 1 既有的名目金額上限)
- `04_paper_trading/run_once.py` — 由 Slice 1 的單標的循序呼叫, 改為兩階段 : 收集階段(對 `SYMBOLS = ["BTCUSDT", "ETHUSDT"]` 各自跑 `data_agent` + `signal_agent`) → 單一 `risk_agent.review_portfolio(...)` 呼叫 → 執行階段(對每個核准的 `OrderEvent` 呼叫 `execution_agent.execute`)
- `.env.example` — 新增 `TELEGRAM_BOT_TOKEN=`、`TELEGRAM_CHAT_ID=` 佔位, 供本地 `.env` 比照填入實際值

**關鍵重用決策** : 相關性計算直接重用收集階段已經為 `signal_agent.decide` 抓取的 OHLCV(開高低收量) 資料, 取其 `close` 欄位算日報酬率相關係數, 不另外發一次網路請求; 這與 Slice 1「訊號用的數據來源與歷史抓取共用同一段程式碼」的重用精神一致.

## 資料流 (data flow) — 單次執行逐步說明

1. **載入每日風控狀態** : `daily_risk_state.load_daily_state(...)`. 若儲存的 `utc_date` 不等於今天(UTC), 以當前帳戶淨值重置 `day_start_equity_usdt` 並存檔; 否則沿用已儲存的基準值.

2. **收集階段** — 對 `SYMBOLS` 中每個標的 :
   - `data_agent.fetch_latest_candles(symbol)` 抓取最新 K 線(沿用 Slice 1 邏輯, 數據不足會拋 `ValueError`, 沿用「寧可整段失敗也不用不完整數據」原則, 但範圍縮小為「該標的」失敗, 不影響另一個標的, 見下方錯誤處理)
   - 用最後一根已收盤 K 線的 `close_time` 與現在時間比較, 依「K 線週期的 1.5 倍」門檻判斷是否過期
   - 未過期 : 呼叫 `signal_agent.decide(ohlcv_dataframe, symbol)` 得到 `SignalEvent`, 並保留該 DataFrame 的 `close` 序列供後續相關性計算使用
   - 已過期 : 不產生信號(過期的數據不該拿來決策), 記錄該標的為「數據異常」, 待 `review_portfolio` 統一轉成 `RejectionEvent` 並觸發警報

3. **查詢帳戶狀態(一次)** : 透過 `binance_testnet_client.get_account_balances()` 取得各標的目前倉位(沿用 Slice 1 的 `determine_current_position`, 含粉塵 (dust) 門檻判斷)與換算後的帳戶總淨值 `account_equity_usdt`.

4. **單一 `risk_agent.review_portfolio(...)` 呼叫**, 內部依序 :
   - **全域每日熔斷檢查(僅一次)** : 若 `(day_start_equity_usdt - account_equity_usdt) / day_start_equity_usdt > 0.04`, 所有標的皆回報 `RejectionEvent`(原因 : 每日熔斷已觸發), 觸發一次 Telegram 警報, 不再往下做其餘檢查
   - **逐標的數據異常檢查** : 收集階段標記為過期的標的, 直接回報 `RejectionEvent`, 觸發一次 Telegram 警報(同一次執行內若有多個標的同時過期, 仍只發一次警報, 避免洗版)
   - **逐標的目標倉位比對** : 與 Slice 1 相同的三分支(相同 → `None`; 多單 → 空手 → 全部平倉 `OrderEvent`, 不做以下四項開倉檢查; 空手 → 多單 → 進入下一步開倉檢查)
   - **開倉方向四項檢查(依序, 任一失敗即回報對應原因的 `RejectionEvent`, 不繼續檢查後續項目)** :
     a. **單筆最大虧損** : `數量 × atr_stop_multiplier × 平均真實區間 (ATR)` 除以 `account_equity_usdt`, 超過 1.5% 拒絕
     b. **最大同時持倉數** : 統計「目前真實持有 + 本次批次中依 `SYMBOLS` 固定順序已核准開倉」的同類別(目前只有加密貨幣)標的數量, 達到類別上限即拒絕
     c. **相關性限制** : 「現有持倉」定義為兩個來源的聯集 — 交易所當前真實持有的標的, 以及本次批次中依 `SYMBOLS` 固定順序已核准開倉的標的; 候選標的與其中任一者的收盤價日報酬率相關係數超過 0.8 即拒絕; 若因抓取失敗等原因缺少足夠重疊歷史導致無法計算相關係數, 視為無法確認風險, 直接拒絕(寧可保守拒絕, 不猜測)
     d. **名目金額上限**(Slice 1 既有邏輯, 沿用不變)
   - 全部通過 → `OrderEvent`

5. **執行階段** : 對每個核准的 `OrderEvent`, 呼叫 `execution_agent.execute(...)`(沿用 Slice 1 邏輯不變) → `FillEvent` 或 `FailEvent`.

6. **存檔** : 若第 1 步發生了每日狀態重置, 寫回 `daily_risk_state.json`; 逐標的把收集、風控、執行三階段的結果記錄成 `run_log.jsonl` 的新行, 與 Slice 1 精神一致.

**需要事先說明的行為後果** : 由於「最大同時持倉數」與「相關性限制」的比較基準包含「本次批次已核准開倉的標的」, 若 BTC 與 ETH 同時從空手轉為都該開多單, 依 `SYMBOLS` 固定順序(BTC 優先於 ETH), BTC 會先被核准開倉; ETH 隨後會拿 BTC 剛核准的部位去做相關性比較 — 而 BTC / ETH 日報酬率的歷史相關係數通常明顯高於 0.8, ETH 很可能因此被拒絕. 這是相關性限制規則設計上「本來就該擋下」的情境, 不是 Bug, 但代表實務上這個雙標的組合很少會同時持有兩個部位, 提前記錄於此, 避免被誤認為異常.

## 錯誤處理 (error handling)

- **單一標的數據抓取失敗** : 與 Slice 1 的「整段失敗」不同, 現在是多標的獨立管線, 一個標的抓取失敗只讓該標的本次執行記錄失敗, 不影響另一個標的繼續走完整條 pipeline
- **Telegram 發送失敗** : `telegram_alerts.send_alert` 內部捕捉例外並記錄清楚的失敗訊息, 不往外拋, 不影響本次執行的風控決策結果或後續流程
- **每日狀態檔遺失或無法解析** : 視為「尚無基準」, 以當前帳戶淨值重置, 不阻擋交易(該檔案是本地快取, 不是真相來源)
- **相關性計算缺少足夠重疊歷史** : 視為無法確認風險, 直接拒絕開倉(風控規則寧可保守擋下, 不因數據不足而放行)
- **交易所端拒絕、成交狀態不明確、冪等性(idempotency)** : 沿用 Slice 1 既有邏輯不變

## 測試與檔案結構 (testing and file layout)

**純決策邏輯** — 5 條規則的個別函式與 `review_portfolio` 的組合邏輯, 用合成 (synthetic) 輸入寫單元測試, 依本專案 TDD (test-driven development, 測試驅動開發) 慣例撰寫. 這次特別涵蓋邊界值本身(剛好 4% 熔斷門檻、剛好 0.8 相關係數、剛好達到持倉數上限), 修正 Slice 1 事後記錄中「只測明顯高於/低於, 沒測邊界」的已知缺口. 測試檔 : `tests/test_paper_trading_risk_agent.py`(擴充既有檔案).

**`daily_risk_state.py`** — `should_reset_for_new_day` 為純函式單元測試; `load_daily_state` / `save_daily_state` 是本機檔案 I/O(非網路請求), 用 `tmp_path` fixture 寫讀寫往返測試, 與 Slice 1 把「I/O 一律不自動化測試」的原則不同 — 差別在於這裡的 I/O 是決定性的本機檔案操作, 不是不可控的外部網路呼叫, 可以且應該自動化測試. 測試檔 : `tests/test_daily_risk_state.py`(新增).

**`telegram_alerts.py`** — `send_alert` 對真實 Telegram Bot API 的 HTTP 呼叫, 比照 `binance_testnet_client` 的 I/O 邊界慣例, 不在自動化測試中模擬, 作為本切片收尾的一部分手動驗證一次(需要 `.env` 中已填入真實 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`).

**`run_once.py` 兩階段重構後的完整 pipeline** — 與 Slice 1 相同, 不在自動化測試中模擬, 以手動執行 BTC + ETH 雙標的至少各一次作為驗證(含至少一次驗證閉手路徑與, 若當下信號允許, 開倉路徑).

**檔案結構** :

```
04_paper_trading/
  events.py                    (不變)
  binance_testnet_client.py    (不變)
  daily_risk_state.py          (新增)
  telegram_alerts.py           (新增)
  run_once.py                  (修改 : 兩階段編排)
  agents/
    data_agent.py               (不變)
    signal_agent.py             (不變)
    risk_agent.py                (修改 : 新增 5 條規則 + review_portfolio)
    execution_agent.py          (不變)
  logs/                        (gitignore 排除)
    run_log.jsonl
    daily_risk_state.json       (新增)
tests/
  test_paper_trading_risk_agent.py   (擴充)
  test_daily_risk_state.py           (新增)
```

## 實作後記錄: 執行紀錄(2026-07-07 手動驗證)

Slice 2 已完成並對真實 Binance Testnet + 真實 Telegram 跑通兩次 `run_once.py`(緊接著驗證冪等性), 詳見下方.

**重要更正說明(本次驗證發現的既有狀態)**: 開始本次驗證前, `04_paper_trading/logs/run_log.jsonl`(4 行) 與 `daily_risk_state.json`(`equity_at_day_start_usdt` = 57711.733164, 對應同一 UTC 日更早的 05:44 執行) 已存在 —— 顯示同一天稍早已有另一次未留下 Commit 紀錄的手動驗證, 且該次驗證已對真實 Testnet 帳戶送出一筆真實成交 : ETHUSDT SELL 1.0, 均價 1769.33 USDT, 訂單編號 9356029(平倉既有多單). 本次驗證執行 Step 4 之前, 誤將這兩個檔案刪除後才開始執行(未先讀取內容備份), 導致 : (a) 稍早那筆真實成交在本地 `run_log.jsonl` 的紀錄遺失(交易所本身的真實成交紀錄不受影響, 只有本地稽核記錄消失) ; (b) `daily_risk_state.json` 的每日熔斷基準時間點被重設成本次驗證開始時間(10:41 UTC) 而非當日最早的 05:44 UTC 基準, 兩者數值相差約 30 USDT(約 0.05%), 對當日熔斷判斷實務影響可忽略, 但流程上不應該在未確認既有內容前刪除本地狀態檔案. 誠實記錄於此, 供之後查閱.

**Telegram 警報整合驗證**: 獨立執行 `telegram_alerts.send_alert('Slice 2 手動驗證: Telegram 警報整合測試')`, 終端機無任何輸出(`send_alert` 只在缺憑證 / 非 200 回應 / 網路例外時才印訊息, 無輸出即代表 HTTP 200 送出成功), 確認訊息已送達 Telegram 聊天視窗.

**完整測試套件**: `pytest tests/ -v` — 114 passed, 全數通過.

**第一次 `run_once.py` 執行**(2026-07-07T10:41:49Z):
- `daily_risk_state.json` 首次建立, `equity_at_day_start_usdt` = 57681.503164(取自真實 Testnet 帳戶淨值, 數值合理)
- BTCUSDT: `risk_decision` = `NoActionNeeded`(目標倉位與當前倉位相符), `execution_result` = null
- ETHUSDT: `risk_decision` = `NoActionNeeded`, `execution_result` = null
- `fetch_failures` = {}, `stale_symbols` = [], `circuit_breaker_triggered` = false
- `run_log.jsonl` 新增一行紀錄

**第二次 `run_once.py` 執行**(2026-07-07T10:41:57Z, 緊接著再跑一次驗證冪等性):
- BTCUSDT: `risk_decision` = `NoActionNeeded`, `execution_result` = null
- ETHUSDT: `risk_decision` = `NoActionNeeded`, `execution_result` = null
- 與第一次結果完全一致, `daily_risk_state.json` 的 `equity_at_day_start_usdt` 未被覆寫改變, 沒有因重複執行而產生非預期的重複下單 — 冪等性確認成立
- `run_log.jsonl` 新增第二行紀錄(共 2 行)

**誠實列出本次驗證未觸發之規則**: 兩次執行 BTC 與 ETH 皆為「目標倉位與當前倉位相符」的 `NoActionNeeded`, 在 `review_portfolio` 內部只走到「全域每日熔斷檢查」與「逐標的數據異常檢查」這兩關(皆通過, 未觸發), 兩個標的都在「目標倉位比對」這一步就得到 `None`, 完全沒有進入開倉方向的四項檢查. 因此以下規則這次**沒有**被真實觸發過, 只有既有單元測試覆蓋, 尚未有真實 API 下的實測案例:
- 每日熔斷(circuit breaker) 的「真的超過 4% 觸發拒絕」分支(這次檢查有跑, 但條件為假, 只確認了「不誤觸發」, 沒確認「真觸發時 Telegram 警報與全標的拒絕」的路徑)
- 數據延遲保護(data staleness) 的「真的過期觸發拒絕」分支(同上, 只確認了「不誤觸發」)
- 單筆最大虧損上限拒絕
- 最大同時持倉數拒絕
- 相關性限制拒絕(含設計文件上方提到的「BTC 與 ETH 同時開倉時 ETH 很可能被相關性擋下」這個預期情境, 這次因為兩者都沒有開倉信號, 完全沒機會驗證)
- 名目金額上限拒絕(Slice 1 沿用邏輯, 這次也沒被真實觸發)
- 開倉路徑本身(`OrderEvent` 買進) 與平倉路徑(`OrderEvent` 賣出) 這次都沒有發生 — 兩個標的當下的凍結策略信號與帳戶當前倉位剛好一致, 完全沒有真實下單

這次驗證證明的是: 管線串接無誤(data → signal → risk → execution 兩階段編排跑通兩個標的)、真實帳戶狀態查詢正常、每日狀態檔案建立與讀取正常、Telegram 警報通道本身可用、`NoActionNeeded` 這個最常見情境下的冪等性成立. 尚未證明的是上述所有「拒絕」與「真實下單」路徑在真實環境下的行為 — 這些留待之後真的遇到對應市場條件時的下一次自然驗證, 或視需要另外安排一次有意觸發條件的手動驗證.
