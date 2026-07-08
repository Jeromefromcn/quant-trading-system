# Phase 3 紙上交易 (paper trading) 執行摘要 Telegram 通知設計文件

日期 : 2026-07-08
狀態 : 已核准 (approved), 待寫實作計劃 (implementation plan)

## 背景 (background)

`04_paper_trading/scheduler.py` 已能每 4 小時無人值守執行一次 `run_once.run_once()`, 並在排程鎖已被持有與執行拋出未預期例外這兩種異常情況下發 Telegram 警報, 詳見 `docs/superpowers/specs/2026-07-08-phase3-paper-trading-scheduler-design.md`. 但正常完成的執行目前完全靜默 : 使用者要知道某次排程有沒有交易, 交易結果如何, 只能自己去讀 `logs/run_log.jsonl`. 使用者希望每次排程執行完後主動收到一則 Telegram 訊息, 告知本次有沒有交易, 以及本次交易的人類可讀摘要, 並且能用開關關閉這則通知(不影響既有的熔斷/數據異常/失敗告警) .

## 目標與範圍 (goal and scope)

**目標** : `scheduler.py` 在 `run_scheduled(...)` 成功回傳(即正常完成路徑) 之後, 額外發送一則 Telegram 摘要訊息, 說明本次是否有成交, 並逐標的列出結果; 提供一個程式碼內常數開關可以整個關閉這則通知.

**本次範圍內** :

- `scheduler.py` 新增 `_format_run_summary(record: dict) -> str`, 把 `run_once()` 回傳的 `record` 轉成人類可讀摘要
- `scheduler.py` 新增模組層級常數 `NOTIFY_RUN_SUMMARY`(預設 `True`) 作為開關
- `scheduler.main()` 在正常完成路徑呼叫 `telegram_alerts.send_alert(_format_run_summary(record))`(當開關為 `True` 時)
- 只在排程路徑(`scheduler.py`) 發送, 手動執行 `run_once.py` 不受影響, 維持現況靜默

**明確排除** :

- `fetch_failures` / `stale_symbols` / `circuit_breaker_triggered` 不放進這則摘要訊息 : 這些已有各自獨立的 Telegram 告警路徑(見 `run_once.py` 既有邏輯) , 保持關注點分離, 不重複通知
- 不改動 `run_once.py` 的 `record` 結構, 只在 `scheduler.py` 這一層做格式轉換
- 不做訊息長度截斷或分頁 : 目前固定只有 2 個標的(`BTCUSDT` / `ETHUSDT`) , 訊息長度遠低於 Telegram 4096 字元上限, YAGNI

## 元件 (components)

修改檔案 : `04_paper_trading/scheduler.py`

- 新常數 `NOTIFY_RUN_SUMMARY = True`, 定義在 `SCHEDULER_LOCK_PATH` 旁邊, 改成 `False` 即可關閉此通知(不影響鎖已持有/執行失敗這兩種既有告警)
- 新函式 `_format_run_summary(record: dict) -> str` :
  - 標頭行 : `Paper trading 執行摘要 (<run_started_at 轉成可讀的 UTC 時間字串>)`, 接一行 `本次有成交` 或 `本次無成交`(依 `record["symbols"]` 裡是否存在任一 `execution_result.type == "FillEvent"` 判斷)
  - 逐一走訪 `record["symbols"]`(key 為標的代號) , 依 `risk_decision.type` 產出一行文字 :
    - `NoActionNeeded` 時 : `<symbol>: 本次無動作`
    - `RejectionEvent` 時 : `<symbol>: 交易被風控擋下 (<reason>, 實際值=<computed_value>, 上限=<limit_value>)`
    - `OrderEvent` 且 `execution_result.type == "FillEvent"` 時 : `<symbol>: <買入/賣出> <quantity> @ <average_price> 成交 (order_id=<order_id>)`
    - `OrderEvent` 且 `execution_result.type == "FailEvent"` 時 : `<symbol>: 下單失敗 (<reason>)`
  - 已 fetch 失敗或數據陳舊而被 `run_once.py` 跳過的標的, 本來就不會出現在 `record["symbols"]` 裡(見 `run_once.py` 現有邏輯的 `continue`) , 因此摘要自然不會提到它們, 不需要額外處理
- `main()` : 在 `record = run_scheduled(...)` 成功回傳後(原本正常完成, 不發告警的分支) , 若 `NOTIFY_RUN_SUMMARY` 為真, 呼叫 `telegram_alerts.send_alert(_format_run_summary(record))`; 其餘印出摘要到 stdout, `exit 0` 的行為不變

**關鍵重用決策** : 沿用既有的 `telegram_alerts.send_alert`(已保證不拋例外, 失敗只記錄) , 不新增通知管道或重試邏輯.

## 資料流 (data flow)

1. `scheduler.main()` 呼叫 `run_scheduled(SCHEDULER_LOCK_PATH)` 並成功取得 `record`
2. 若 `NOTIFY_RUN_SUMMARY` 為 `True` : 呼叫 `_format_run_summary(record)` 產生摘要文字, 交給 `telegram_alerts.send_alert(...)` 送出
3. 印出精簡結果摘要到 stdout(既有行為) , `exit 0`

鎖搶不到與 `run_once()` 拋未預期例外這兩條路徑不變, 仍各自發既有的告警, 不受本次改動影響.

## 錯誤處理 (error handling)

- `telegram_alerts.send_alert` 本身已保證不拋例外(缺憑證/網路失敗只印出訊息並返回) , `_format_run_summary` 是純字串組裝, 不會失敗; 因此本次改動不需要額外的例外處理
- `_format_run_summary` 只依賴 `run_once()` 既有 record 結構裡一定存在的欄位(`risk_decision.type` 必為 `NoActionNeeded`/`OrderEvent`/`RejectionEvent` 三者之一, `execution_result` 只在 `OrderEvent` 時非 null 且必為 `FillEvent`/`FailEvent` 之一, 見 `run_once.py` 與 `events.py`) , 不需要對未知型別做防禦性處理

## 測試 (testing)

`tests/test_paper_trading_scheduler.py` :

- `_format_run_summary` 單元測試(直接餵手造的 `record` dict, 不需要跑真正的 `run_once`) :
  - 全部標的皆 `NoActionNeeded` 時, 標頭為 `本次無成交`, 逐標的列出 `本次無動作`
  - 含一個 `FillEvent` 時, 標頭為 `本次有成交`, 該標的行含買賣方向, 數量, 成交價, order_id
  - 含一個 `RejectionEvent` 時, 該標的行含 reason, computed_value, limit_value
  - 含一個 `FailEvent` 時, 該標的行含下單失敗與 reason
- 更新既有的 `test_main_exits_zero_without_alert_when_successful`(目前斷言正常完成時 `alerts == []`, 這個假設在本次改動後不再成立) : 改成斷言正常完成時 `telegram_alerts.send_alert` 被呼叫一次, 且訊息內容來自 `_format_run_summary`
- 新增 `test_main_does_not_send_summary_when_notify_disabled` : 以 `monkeypatch.setattr(scheduler, "NOTIFY_RUN_SUMMARY", False)` 關閉開關, 斷言正常完成時 `telegram_alerts.send_alert` 未被呼叫
- 沿用既有慣例 : `telegram_alerts.send_alert` 全程 mock, 不對外發真實請求

## 部署 (deployment)

無需額外部署步驟 : `scheduler.py` 已在 crontab 排程中, 本次只是行為擴充, 隨下一次 `git push` 後的排程執行自動生效. 若使用者事後想關閉通知, 只需把 `NOTIFY_RUN_SUMMARY` 改成 `False` 並提交.
