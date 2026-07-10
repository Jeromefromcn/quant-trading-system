# Phase 3 紙上交易 (paper trading) 美股切片設計文件: Alpaca Paper Trading 整合

日期: 2026-07-10
狀態: 已核准 (approved), 待寫實作計劃 (implementation plan)

## 背景 (background)

加密貨幣側的 Phase 3 紙上交易 pipeline 已建好並跑通: `data_agent` → `signal_agent` → `risk_agent` → `execution_agent` 對 BTC/USDT + ETH/USDT 雙標的每 4 小時執行一次(Binance Testnet), 5 條風控硬性規則、每日熔斷狀態、Telegram 警報、排程器 (scheduler)、每日彙總報告 (`monitor.py`) 皆已完成. 詳見 `docs/superpowers/specs/2026-07-06-phase3-paper-trading-slice1-design.md`、`2026-07-06-phase3-paper-trading-slice2-risk-rules-design.md`、`2026-07-08-*` 三份排程/監控文件.

`project_manage/ROADMAP.md` 的 Phase 3 一直保留「美股每個交易日一次」這個未勾選項目, 原文寫的執行方式是「收盤後算信號, 次日開盤前 30 分鐘掛限價單」. `risk_agent.py` 的 `SYMBOL_MARKET_TYPES` 與 `max_positions_by_market` 也早已預留 `"stocks": 5` 的欄位, 只是尚無美股標的真正用到.

策略研究層面, `exp_002` 凍結參數已在 `exp_007`(SPY)、`exp_008`(QQQ) 上做過跨市場泛化驗證(見 `project_manage/STRATEGY_LOG.md` 2026-07-06 記錄): 樣本外全部正報酬、正 Sharpe, 但樣本數小 (SPY 8 筆、QQQ 5 筆), 且後續因子迴歸分析顯示這段報酬統計上更接近「動能/趨勢溢價的 beta 曝險」而非獨立 alpha. 本切片的目的**不是**驗證「這裡有 alpha」, 而是驗證「這個已知的溫和趨勢曝險, 在美股真實執行摩擦(開盤拍賣、限價保護、交易日曆)下能不能穩定捕捉到」— 與加密貨幣側 Phase 3 的定位一致.

## 目標與範圍 (goal and scope)

**目標**: 新增一條獨立的美股紙上交易 pipeline(SPY + QQQ, Alpaca Paper Trading), 重用既有的 `signal_agent` / `risk_agent` 決策邏輯與凍結的 `exp_002` 參數, 每個交易日收盤後執行一次, 用 limit-on-open (LOO, 開盤限價) 委託單完成次日開盤附近的進場保護.

**本切片範圍內**:

- 交易標的: `["SPY", "QQQ"]`, 皆屬 `risk_agent.SYMBOL_MARKET_TYPES` 的 `"stocks"` 類別
- 獨立於加密貨幣的資金池與風控狀態: 各自獨立的 `run_log_stocks.jsonl`、`daily_risk_state_stocks.json`, 不與加密貨幣的帳戶淨值合併計算每日熔斷(兩個交易所帳戶本來就是獨立資金, 且跨市場相關性/熔斷研究屬於 ROADMAP Phase 2 Round 4 尚未開始的項目, 不該在工程層先斬先奏)
- 新增 `alpaca_paper_trading_client.py`(對 `paper-api.alpaca.markets` 簽名較簡單的 API-Key 驗證, 用於查帳戶、查倉位、查交易日曆、下單)
- 進場用 limit-on-open (`time_in_force=opg`, 限價 = 收盤時算出的最新收盤價), 出場用 market-on-open (`time_in_force=opg`, 市價), 皆由交易所在次日開盤拍賣時撮合, 未成交(僅限進場的限價單可能發生)由交易所自動取消 — 不自建「收盤後算信號 + 開盤前另一支程式下單」的兩段式排程, 單一每日執行即可完成委託
- 重用 `signal_agent.py`、`risk_agent.py`(僅新增 `SYMBOL_MARKET_TYPES` 條目)、`daily_risk_state.py`、`telegram_alerts.py`、`events.py`(新增一個可選欄位與一個新事件型別, 皆為加法, 不影響加密貨幣既有行為)
- 交易日曆檢查: 查 Alpaca `/v2/calendar`, 非交易日(週末/假日)時本次執行記錄為安靜的無動作 (no-op), 不產生信號也不發警報
- 前置手動設定: 把 Alpaca Paper 帳戶餘額重設為 10,000 USD, 對齊 `exp_002` 凍結的 `initial_capital`(見下方「前置設置事項」)

**明確排除, 留給後續切片或研究**:

- 加密貨幣與美股合併計算的組合風控 (portfolio-level circuit breaker / correlation), 對應 ROADMAP Phase 2 Round 4「加密 + 美股同時持倉的相關性分析」, 尚未研究, 不在工程上先做
- 分數股 (fractional share) 下單
- SPY/QQQ 以外的美股標的(架構上與加密貨幣 Slice 2 擴展 ETH 的方式相同, 之後只需在 `SYMBOLS` 與 `SYMBOL_MARKET_TYPES` 加一行)
- 盤中 / WebSocket 即時數據(理由同加密貨幣側: 日線決策不需要次秒級數據)

## 前置設置事項 (manual pre-flight, 非程式碼)

- 登入 Alpaca Paper Trading 後台, 用 Reset Account 功能把模擬資金重設為 **10,000 USD**, 對齊 `exp_002_ema_adx/config.py` 的 `initial_capital=10_000.0`. 若沿用 Alpaca 預設的 100,000 USD, `compute_buy_quantity` 會以真實帳戶淨值(10 倍於假設值)計算部位, 而名目金額上限檢查卻是以 `initial_capital × max_position_fraction` 為天花板, 會導致幾乎每筆開倉都因「超過名目金額上限」被風控拒絕
- 確認 `.env` 中既有的 `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET_KEY` 對 `paper-api.alpaca.markets`(交易端點) 同樣有效, 不只是對 `data.alpaca.markets`(行情端點, Phase 0-2 已在用) 有效 — 同一組 Alpaca Paper 帳戶金鑰本應兩者通用, 若不通用需另外申請

## 元件 (components)

新增檔案:

- `04_paper_trading/alpaca_paper_trading_client.py` — 對應 `binance_testnet_client.py`. 用 `APCA-API-KEY-ID` / `APCA-API-SECRET-KEY` 標頭驗證(比 Binance 的 HMAC 簽名簡單, 不需組簽名字串). 提供:
  - `get_account() -> dict`: 回傳 `{"equity": float, "cash": float}`
  - `get_positions() -> dict`: 回傳 `{symbol: 持有股數}`, 只含非零倉位
  - `get_todays_calendar_entry() -> dict | None`: 查 `/v2/calendar?start=today&end=today`, 無資料代表今天非交易日
  - `place_limit_on_open_order(symbol, side, quantity, limit_price) -> (status_code, response)`: `type=limit, time_in_force=opg`
  - `place_market_on_open_order(symbol, side, quantity) -> (status_code, response)`: `type=market, time_in_force=opg`
  - `round_quantity_down_to_whole_shares(quantity) -> int`: 純函式, 無分數股, 向下取整
- `04_paper_trading/agents/stock_data_agent.py` — 對應 `agents/data_agent.py`. 重用 `02_data/fetchers/alpaca_fetcher.fetch_full_history_daily_bars`(不修改該檔案), 以「今天往回推約 200 個日曆天」當 `start_date`, 取回後保留最後 `lookback_bars`(預設 100, 與加密貨幣側同一套暖身期理由: exp_002 的 Wilder 平滑指標) 根. 根數不足時拋 `ValueError`, 與 `data_agent.fetch_latest_candles` 邏輯對稱
- `04_paper_trading/agents/stock_execution_agent.py` — 對應 `agents/execution_agent.py`. 買進呼叫 `place_limit_on_open_order`(限價 = `signal_event.latest_close_price`), 賣出(出場) 呼叫 `place_market_on_open_order`. 委託單在收盤後送出、尚未到開盤拍賣, 因此不會立即成交, 回傳新事件型別 `SubmittedEvent`(見下方 `events.py` 變更), 不嘗試輪詢成交狀態(那要等到明天開盤, 見下方「錯誤處理」)
- `04_paper_trading/run_once_stocks.py` — 對應 `run_once.py`. `SYMBOLS = ["SPY", "QQQ"]`. 開頭先做交易日曆檢查; 其餘流程(收集 → `risk_agent.review_portfolio` → 執行 → 寫 `run_log_stocks.jsonl`)與加密貨幣側 Slice 2 的兩階段編排相同, 只是資料來源/執行客戶端換成 Alpaca, 且 `OrderEvent` 一律走 LOO/MOO 而非立即市價單. `RISK_LIMITS` 沿用與加密貨幣側完全相同的數值(同一套風控哲學, 沒有理由讓美股比較寬鬆或嚴格): `max_loss_per_trade_fraction=0.015, max_daily_loss_fraction=0.04, max_positions_by_market={"crypto": 3, "stocks": 5}, max_correlation=0.8`. 每日狀態的帳戶淨值鍵名為 `equity_at_day_start_usd`(對稱加密貨幣側的 `..._usdt`, 但幣別不同故字尾不同)
- `04_paper_trading/scheduler_stocks.py` — 對應 `scheduler.py`. 同樣的 `fcntl.flock` 防重疊鎖(獨立鎖檔 `logs/scheduler_stocks.lock`), 呼叫 `run_once_stocks.run_once()`, 失敗與正常完成後的 Telegram 摘要邏輯相同(no-op 執行不發摘要, 避免每個非交易日洗版)
- `04_paper_trading/monitor_stocks.py` — 對應 `monitor.py`. 讀 `run_log_stocks.jsonl`, 彙總前一個執行日的委託與帳戶淨值. 与加密貨幣版的關鍵差異: 顯示的是「已送出的開盤委託」(`SubmittedEvent`), 不是「已確認成交」, 並額外顯示「今日實際持倉」(來自當天執行時查詢到的真實 Alpaca 倉位, 間接反映前一交易日委託單是否成交)

修改檔案(皆為加法, 不影響加密貨幣既有行為):

- `04_paper_trading/agents/risk_agent.py` — `SYMBOL_MARKET_TYPES` 新增 `"SPY": "stocks", "QQQ": "stocks"` 兩個條目
- `04_paper_trading/events.py`:
  - `OrderEvent` 新增可選欄位 `limit_price: float | None = None`(加密貨幣的市價單不設, 維持 `None`; `review_portfolio` 對 `"stocks"` 類別的核准開倉單, 額外填入 `signal_event.latest_close_price`)
  - 新增 `SubmittedEvent` dataclass: `symbol, side, quantity, order_id, limit_price: float | None`(出場單無限價, 為 `None`), 代表「委託已被交易所接受, 尚未確認成交」, 與 `FillEvent`(已確認成交) 語意上明確分開, 避免誤把「送出」當「成交」記錄
- `.env.example` — 無新增(既有的 `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET_KEY` / `ALPACA_PAPER_BASE_URL` 三個佔位符直接沿用)

## 資料流 (data flow) — 單次執行逐步說明

1. **交易日曆檢查**: `alpaca_paper_trading_client.get_todays_calendar_entry()`. 若為 `None`(週末/假日), 記錄一筆 `{"market_open": false}` 的 no-op 執行紀錄, 直接結束, 不產生信號, 不查帳戶, 不發 Telegram
2. **載入每日風控狀態**: 沿用 `daily_risk_state.py`, 讀寫改指向 `logs/daily_risk_state_stocks.json`(獨立於加密貨幣的基準值)
3. **收集階段** — 對 `SYMBOLS` 中每個標的:
   - `stock_data_agent.fetch_latest_daily_bars(symbol)` 抓最新日線
   - 用 `risk_agent.check_data_staleness`(沿用不變, `bar_interval=timedelta(days=1)`) 判斷是否過期
   - 未過期 → `signal_agent.decide(...)` 得 `SignalEvent`; 已過期 → 標記數據異常, 待風控階段統一轉 `RejectionEvent`
4. **查詢帳戶狀態(一次)**: `alpaca_paper_trading_client.get_account()` 取 `equity`; `get_positions()` 取各標的目前股數, 換算成 0/1(沿用 `risk_agent.determine_current_position`, 同一套粉塵門檻邏輯對股票同樣適用)
5. **單一 `risk_agent.review_portfolio(...)` 呼叫**: 與加密貨幣側完全相同的函式與規則順序(全域熔斷 → 逐標的數據異常 → 逐標的目標倉位比對 → 開倉四項檢查), 差別只在傳入的 `SYMBOLS`/`market_type` 落在 `"stocks"` 類別、`max_positions_by_market["stocks"]=5`. **預期會頻繁觸發的情境**: SPY 與 QQQ 日報酬率歷史相關係數通常 > 0.8, 兩者同時從空手轉多單時, 依固定順序先核准的一個會讓另一個在相關性檢查被拒 — 這是既有規則的既定行為, 不是本切片的缺陷(與加密貨幣側 Slice 2 設計文件記錄的 BTC/ETH 情境完全對稱)
6. **執行階段**: 對核准的 `OrderEvent`:
   - `side == "BUY"` → `stock_execution_agent.execute` 呼叫 `place_limit_on_open_order`, 限價取 `order_event.limit_price`
   - `side == "SELL"`(出場) → 呼叫 `place_market_on_open_order`, 不設限價
   - 兩者皆回傳 `SubmittedEvent`(委託已被接受) 或 `FailEvent`(下單請求本身失敗)
7. **存檔**: 寫入 `run_log_stocks.jsonl` 新的一行

**次日的自然核對機制**: 委託單要等到次日開盤拍賣才會撮合. 系統不另外安排「查詢是否成交」的排程 — 次一個交易日的執行從第 4 步 `get_positions()` 查到的是 Alpaca 端真實倉位, 若前一天的 LOO/MOO 委託成交了, 這裡會直接反映為新的持倉, 若未成交(僅可能發生在 LOO 限價單), 持倉不變, 目標倉位比對這一步會用「今天的新信號」重新決定要不要再次嘗試開倉. 這與加密貨幣側「永遠信任交易所真實狀態, 不信任本地記憶」的原則完全一致, 不需要額外的成交確認邏輯.

## 錯誤處理 (error handling)

- **非交易日**: 安靜 no-op, 見資料流第 1 步, 不發 Telegram(避免週末/假日連續洗版)
- **單一標的數據抓取失敗**: 與加密貨幣 Slice 2 相同, 只影響該標的本次執行, 不中止另一標的
- **LOO 限價單未成交**: 交易所自動取消(`time_in_force=opg` 的標準行為), 系統不追蹤取消事件本身, 由次日重新計算信號自然處理(見上「次日的自然核對機制」)
- **下單請求網路例外 / 非 2xx 回應**: 與 `execution_agent.execute` 相同處理原則, 回傳 `FailEvent`, 記錄清楚原因, 不重試(可能已送達交易所, 盲目重試有重複下單風險)
- **相關性限制擋下 SPY/QQQ 同時開倉**: 預期行為, 見資料流第 5 步說明, 不是需要修的錯誤
- **帳戶餘額未重設為 10,000 USD**: 不是程式錯誤, 但會導致名目金額上限規則幾乎必然觸發, 已列入前置設置事項, 若發生應先檢查帳戶餘額而非懷疑風控邏輯

## 測試與檔案結構 (testing and file layout)

- `alpaca_paper_trading_client.py`: `round_quantity_down_to_whole_shares` 純函式單元測試(邊界值: 剛好整數股、小於 1 股); HTTP 請求組裝/驗證標頭邏輯用 mock 測試請求是否正確組成, 不打真實網路
- `stock_data_agent.py`: mock `alpaca_fetcher.fetch_full_history_daily_bars` 的回傳, 驗證 lookback 截取與根數不足時拋錯的邏輯
- `stock_execution_agent.py`: mock client 回應, 驗證 BUY → LOO / SELL → MOO 的分支選擇, 以及 `SubmittedEvent` 與 `FailEvent` 的產生條件
- `risk_agent.py`: 擴充既有 `tests/test_paper_trading_risk_agent.py`, 新增 SPY/QQQ 屬於 `"stocks"` 類別、`max_positions_by_market["stocks"]` 生效的案例
- `run_once_stocks.py`: 比照 `tests/test_paper_trading_run_once.py` 的合成 (synthetic) 輸入模式, mock 掉 Alpaca client 與 agents, 驗證交易日曆 no-op 路徑、單標的失敗不中止全體、`OrderEvent.limit_price` 正確帶入等編排邏輯
- `monitor_stocks.py`: 比照 `tests/test_paper_trading_monitor.py`, 驗證 `SubmittedEvent` 彙總文字與「無執行紀錄」情境
- `scheduler_stocks.py`: 比照 `tests/test_paper_trading_scheduler.py`, 驗證鎖檔防重疊與 no-op 執行不發摘要

真實 Alpaca API 呼叫(下單、查帳戶、查交易日曆) 與加密貨幣側慣例一致, 不在自動化測試中模擬, 作為本切片收尾的手動驗證: 至少一次 no-op(挑週末跑) + 至少一次真實交易日執行(驗證委託送出, 隔日核對是否成交或自動取消).

檔案結構:

```
04_paper_trading/
  events.py                          (修改: OrderEvent.limit_price, 新增 SubmittedEvent)
  alpaca_paper_trading_client.py     (新增)
  run_once_stocks.py                 (新增)
  scheduler_stocks.py                (新增)
  monitor_stocks.py                  (新增)
  agents/
    stock_data_agent.py              (新增)
    stock_execution_agent.py         (新增)
    risk_agent.py                    (修改: SYMBOL_MARKET_TYPES 新增 SPY/QQQ)
  logs/                              (gitignore 排除)
    run_log_stocks.jsonl
    daily_risk_state_stocks.json
    scheduler_stocks.lock
tests/
  test_alpaca_paper_trading_client.py    (新增)
  test_stock_data_agent.py               (新增)
  test_stock_execution_agent.py          (新增)
  test_run_once_stocks.py                (新增)
  test_monitor_stocks.py                 (新增)
  test_scheduler_stocks.py               (新增)
  test_paper_trading_risk_agent.py       (擴充)
  test_paper_trading_events.py           (擴充: SubmittedEvent)
```

## 排程 (crontab)

伺服器所在時區為 `Asia/Hong_Kong`, 美東時間有夏令/冬令時間 (DST) 之分. 若系統 cron 支援 `CRON_TZ` 前綴(Ubuntu 的 cron 通常支援), 用美東時間表示排程, 由 cron 自動處理 DST 轉換:

```
CRON_TZ=America/New_York
35 16 * * 1-5 cd .../04_paper_trading && python3 scheduler_stocks.py >> logs/cron.log 2>&1
0 8 * * 1-5   cd .../04_paper_trading && python3 monitor_stocks.py >> logs/cron.log 2>&1
```

`scheduler_stocks.py` 訂在美東收盤(16:00 ET) 後 35 分鐘執行, 留緩衝時間給 Alpaca 當日收盤資料落地; 週一至週五觸發即可(週末本來就會被交易日曆檢查擋下, 但沒必要讓 cron 白跑). 若目標系統的 cron 不支援 `CRON_TZ`, 退回用 UTC 固定時間表示, 並在實作時人工核對當下的 EST/EDT 對應偏移量, 於下年度 DST 轉換時提醒手動調整這兩行(已知限制, 記錄於此供之後查閱).

`monitor_stocks.py` 排在次日美東開盤前(08:00 ET, 早於 9:30 開盤), 讓每日報告能看到「前一天送出的委託」與「查詢當下的真實持倉」對照.

## ROADMAP 對應

完成後回頭勾選 `project_manage/ROADMAP.md` 中「`scheduler.py`: 美股每個交易日一次」與相關風控規則驗證項目(僅美股部分; 加密貨幣部分已完成), 並在 commit message 中依專案慣例標註.
