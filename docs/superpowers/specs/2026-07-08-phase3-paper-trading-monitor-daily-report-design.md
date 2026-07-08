# Phase 3 紙上交易 (paper trading) 每日報告 (`monitor.py`) 設計文件

日期 : 2026-07-08
狀態 : 已核准 (approved), 待寫實作計劃 (implementation plan)

## 背景 (background)

`04_paper_trading/scheduler.py` 目前每 4 小時執行一次 `run_once.run_once()`, 每次正常完成後會發一則執行摘要 Telegram 通知(見 `docs/superpowers/specs/2026-07-08-phase3-paper-trading-run-summary-notification-design.md`), 加密貨幣一天 6 則. 這是單次執行的摘要, 不是 ROADMAP 上要求的每日報告(含信號, 執行結果, 持倉, 帳戶摘要, 系統健康). 使用者要的是把一整天多次執行的結果彙總成一則每日總結, 方便一眼掌握當天狀況, 不用自己去翻 6 則訊息或讀 `logs/run_log.jsonl`.

## 目標與範圍 (goal and scope)

**目標** : 新增 `04_paper_trading/monitor.py`, 由獨立 crontab 於每天 UTC 00:00 觸發, 讀取 `logs/run_log.jsonl` 中前一個 UTC 日曆天的所有執行紀錄, 彙總成一則每日報告, 透過 `telegram_alerts.send_alert()` 發送.

**本次範圍內** :

- `monitor.py` 三個函式 : `_load_records_for_date`(讀檔 + 依日期過濾)、`_format_daily_report`(純函式, 組報告文字)、`main()`(串接兩者並發送)
- 報告內容 : 成交交易列表、執行次數與風控拒絕次數統計、帳戶淨值變化、最新持倉明細、系統健康(數據異常/熔斷觸發次數)
- 當日無任何執行紀錄時仍發送報告, 明確標註: 當日無任何執行紀錄

**明確排除** :

- 不新增 crontab 設定本身(部署段落只記錄要新增的一行, 實際 `crontab -e` 由使用者手動操作或另行確認)
- 不修改 `run_once.py` 的 record 結構或 `scheduler.py` 的既有邏輯, `monitor.py` 只讀既有的 `run_log.jsonl`, 不寫入
- 不處理美股(尚未接上排程, 見 ROADMAP), 不做 log 檔案輪替(rotation) 或壓縮, YAGNI
- 不逐次列出無動作或無成交的執行明細, 只列成交交易 + 統計數字(比照 `scheduler._format_run_summary` 已確立的只講重要的事原則)

## 元件 (components)

新增檔案 : `04_paper_trading/monitor.py`

- 模組常數 `LOG_FILE_PATH`(沿用 `run_once.py` 的 `logs/run_log.jsonl` 路徑) 與 `EXPECTED_RUNS_PER_DAY = 6`(目前 crontab 每 4 小時觸發一次, 一天 6 次; 若未來排程頻率改變需同步修改此常數, 註解註明來源)
- `_load_records_for_date(log_file_path: str, target_date: date) -> list[dict]` :
  - 逐行讀 jsonl(檔案不存在時視為空列表, 不拋例外)
  - 每行 parse `run_started_at`(ISO 格式含時區) 轉成 UTC 後取 `.date()`, 等於 `target_date` 才保留
  - 依檔案原本寫入順序回傳(`run_once.py` 是 append-only, 天然依時間序)
- `_format_daily_report(records: list[dict], target_date: date) -> str` :
  - 標題行 : `每日報告 (<target_date> UTC)`
  - `records` 為空 : 標題後只接一行當日無任何執行紀錄的提示文字, 直接回傳, 不產生後續段落
  - 成交交易段 : 走訪所有 record 的 `symbols`, 篩出 `execution_result.type == "FillEvent"`, 逐筆輸出 `<run_started_at 以 "%H:%M UTC" 格式化> <symbol>: <買入/賣出> <quantity> @ <average_price>`; 若整天無成交輸出今日無成交
  - 統計行 : `今日排程執行 <len(records)> / 預期 <EXPECTED_RUNS_PER_DAY> 次` + `風控拒絕 <N> 次`(N = 所有 record 所有 symbol 中 `risk_decision.type == "RejectionEvent"` 的總數)
  - 帳戶摘要段 : 取 `records[0]["day_start_equity_usdt"]` 為組點淨值, `records[-1]["account_equity_usdt"]` 為結束淨值, 算漲跌 `(結束-組點)/組點 * 100%`, 輸出 `帳戶淨值從 <組點> 變化至 <結束> USDT (<±X.XX%>)`
  - 持倉明細段 : 取 `records[-1]["symbols"]`, 對每個 symbol, 若 `current_base_asset_balance != 0` 且該 symbol 有 `signal` 欄位, 輸出 `<symbol>: <balance> (約 <balance * latest_close_price> USDT)`; 全部為 0 時輸出目前無持倉
  - 系統健康段 : `數據異常保護觸發 <M> 次`(M = `stale_symbols` 非空的 record 數) + `每日熔斷觸發 <K> 次`(K = `circuit_breaker_triggered == True` 的 record 數)
- `main()` : 計算 `target_date = datetime.now(timezone.utc).date() - timedelta(days=1)`(00:00 觸發時彙總剛結束的那一天), 呼叫 `_load_records_for_date` 讀檔, 呼叫 `_format_daily_report` 組文字, 呼叫 `telegram_alerts.send_alert(...)` 送出; 印出精簡結果到 stdout(比照 `run_once.py` / `scheduler.py` 慣例)

**關鍵重用決策** : 沿用 `telegram_alerts.send_alert`(已保證不拋例外) 與 `run_once.py` 既有的 record 結構欄位, 不新增資料模型或修改既有檔案.

## 資料流 (data flow)

1. crontab 於 UTC 00:00 執行 `python3 monitor.py`
2. `main()` 算出 `target_date`(前一個 UTC 日曆天), 呼叫 `_load_records_for_date(LOG_FILE_PATH, target_date)` 取得當日所有 record
3. `_format_daily_report(records, target_date)` 產生報告文字(純函式, 不碰檔案/網路)
4. `telegram_alerts.send_alert(report_text)` 送出; 印出簡短結果到 stdout

## 錯誤處理 (error handling)

- `_load_records_for_date` : log 檔案不存在時回傳空列表, 不拋例外(每日報告本身不該因為排程還沒跑過而失敗); 個別行 JSON 解析失敗時略過該行並印出警告到 stderr, 不中止整份報告(單一髒行不該讓整天的報告發不出去)
- `_format_daily_report` 是純字串組裝, 只依賴 `run_once.py` 既有 record 結構裡保證存在的欄位(`account_equity_usdt`、`day_start_equity_usdt`、`stale_symbols`、`circuit_breaker_triggered`、`symbols[*].risk_decision.type`), 不需要防禦性處理
- `telegram_alerts.send_alert` 已保證不拋例外, `monitor.py` 不需額外 try/except 包住發送步驟

## 測試 (testing)

新增 `tests/test_paper_trading_monitor.py`, 比照 `tests/test_paper_trading_scheduler.py` 風格 :

- `_load_records_for_date` :
  - 用 `tmp_path` 建暫存 jsonl, 寫入跨 UTC 日期邊界的兩筆(例如 `23:59:59+00:00` 與隔天 `00:00:01+00:00`), 驗證只回傳目標日期那一筆
  - 檔案不存在時回傳空列表, 不拋例外
- `_format_daily_report`(純函式, 手工建構 records list, 不需真正跑 `run_once`) :
  - 空列表時只輸出當日無任何執行紀錄的提示文字
  - 含一筆 `FillEvent` 時成交段列出方向/數量/價格
  - 全天皆無成交時輸出今日無成交
  - 含 `RejectionEvent` 時統計行的拒絕次數正確累加
  - 帳戶淨值段的漲跌 % 計算正確(含淨值下跌的負值情境)
  - 持倉明細正確略過餘額為 0 的標的
  - `stale_symbols` 與 `circuit_breaker_triggered` 的觸發次數統計正確
- `main()` : mock `_load_records_for_date` 與 `telegram_alerts.send_alert`, 驗證兩者依序被正確呼叫, 且 `target_date` 計算為執行當下 UTC 日期減一天(全程不碰真實檔案或網路)

## 部署 (deployment)

程式碼隨 `git push` 上線後, 需額外新增一行獨立的 crontab 排程(與現有加密貨幣排程分開, 互不影響) :

```
0 0 * * * cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && python3 monitor.py
```

此行由使用者手動確認後自行加入 crontab(比照 `docs/superpowers/specs/2026-07-08-phase3-paper-trading-scheduler-design.md` 的部署慣例, 不在程式碼變更範圍內自動生效).
