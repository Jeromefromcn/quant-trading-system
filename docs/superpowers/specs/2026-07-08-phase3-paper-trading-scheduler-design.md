# Phase 3 紙上交易 (paper trading) 排程器 (scheduler) 設計文件

日期 : 2026-07-08
狀態 : 已核准 (approved), 待寫實作計劃 (implementation plan)

## 背景 (background)

Slice 2 已完成並對真實 Binance Testnet 帳戶手動跑通兩次 `run_once.py`, 確認 data → signal → risk → execution 全鏈路正常、冪等性 (idempotency) 成立, 詳見 `docs/superpowers/specs/2026-07-06-phase3-paper-trading-slice2-risk-rules-design.md` 的「實作後記錄」段落. 但目前每次執行都要手動觸發, `04_paper_trading/scheduler.py` 仍是空檔案.

依 `project_manage/ROADMAP.md` 的「調度與通知」段落, 加密貨幣標的應每 4 小時執行一次 (00:00 / 04:00 / 08:00 / 12:00 / 16:00 / 20:00 UTC). 本文件只處理加密貨幣的排程自動化, 不涉及美股 (Alpaca) 整合或每日彙總報告 (`monitor.py`) —— 兩者都是各自獨立的關注點, 留給後續切片另開規格.

## 目標與範圍 (goal and scope)

**目標** : 讓 `run_once.py` 能在無人值守的情況下, 每 4 小時自動執行一次, 並在「執行失敗」與「上次執行尚未結束」這兩種異常情況下主動發出 Telegram 警報 (而不是靜默失敗, 只留在 cron 預設寄不出去的郵件裡).

**本切片範圍內** :

- `04_paper_trading/scheduler.py` : 包住 `run_once.run_once()` 的排程安全網, 提供防重疊執行的鎖與失敗告警
- 外部觸發機制 : 系統 crontab 新增一行, 在 6 個固定 UTC 時間點呼叫 `scheduler.py`
- 執行紀錄導向 `04_paper_trading/logs/cron.log` (gitignore 排除, 與既有 `run_log.jsonl` 同一層級)

**明確排除, 留給後續切片** :

- Alpaca 美股整合, 以及美股所需的「是否為交易日 / 是否過了收盤時間」判斷邏輯 (加密貨幣市場 24/7 開盤, 不需要這類判斷, 直接用固定 UTC 時間點觸發即可)
- `monitor.py` 每日彙總報告 (與本文件的「失敗即警報」是不同關注點 : 這裡是異常才通知, 每日報告則是不論有無異常都定期彙總)
- systemd timer 或其他排程機制 (這台機器已在用 crontab 跑其他排程任務, 沿用現有慣例)

## 元件 (components)

新增檔案 :

- `04_paper_trading/scheduler.py` :
  - `run_scheduled(lock_file_path: str) -> None` : 以 `fcntl.flock(LOCK_EX | LOCK_NB)` 對 `lock_file_path` 嘗試取得非阻塞的獨占鎖. 取得鎖時呼叫 `run_once.run_once()`; 鎖仍由作業系統持有直到函式回傳或 process 結束才釋放 (crash 時核心會自動釋放, 不會留下無法清除的殘留鎖). 搶不到鎖時拋出自訂的 `SchedulerLockedError`, 交給 `main()` 統一處理告警, 本函式不自己發警報 (保持單一職責, 方便測試以 mock 驗證)
  - `main() -> None` : 呼叫 `run_scheduled(...)`, 依結果分三種情況處理 :
    - 正常完成 : 印出精簡結果摘要到 stdout, exit 0
    - `SchedulerLockedError` : 呼叫 `telegram_alerts.send_alert("排程跳過: 上一次執行尚未結束")`, 印出說明到 stderr, exit 0 (這是預期中會發生、已妥善處理的情況, 不是失敗)
    - 其他任何例外 (`run_once()` 內部拋出的) : 呼叫 `telegram_alerts.send_alert(f"排程執行失敗: {error}")`, 印出完整 traceback 到 stderr, exit 1 (讓 cron 的結果碼與 log 都能反映這是一次真正的失敗)
  - 鎖檔預設路徑 `04_paper_trading/logs/scheduler.lock`, 透過模組層級常數定義, 測試時可覆寫

修改檔案 :

- 無 (`run_once.py` 的 `run_once()` 函式簽名已經是可直接呼叫的形式, 不需要改動)

**關鍵重用決策** : 沿用 `run_once.py` 現有的 `sys.path.insert` 手法, 讓 `scheduler.py` 能直接 `import run_once`, 不引入新的專案結構或打包方式.

## 資料流 (data flow)

1. Crontab 在 6 個 UTC 時間點之一觸發, 執行 `cd 04_paper_trading && python3 scheduler.py`, stdout/stderr 皆導向 `logs/cron.log`
2. `scheduler.py main()` 呼叫 `run_scheduled(SCHEDULER_LOCK_PATH)`
3. `run_scheduled` 嘗試取得 `logs/scheduler.lock` 的獨占鎖
   - 取得成功 : 呼叫 `run_once.run_once()`, 回傳其結果字典
   - 取得失敗 (上次執行仍持有鎖) : 拋出 `SchedulerLockedError`
4. `main()` 依步驟 3 的結果分流 (見上方元件段落), 決定要不要發 Telegram 警報與最終 exit code
5. 鎖隨 process 結束自動釋放, 供下一次排程觸發使用

## 錯誤處理 (error handling)

- `run_once()` 內部各標的的資料抓取失敗、風控拒絕等, 都已經是 `run_once()` 正常回傳值的一部分 (見 Slice 2 設計文件), 不會以例外形式傳到 `scheduler.py` —— 這些情況早已有對應的 Telegram 警報路徑 (熔斷、數據異常), `scheduler.py` 不重複處理
- `scheduler.py` 只關心兩種它自己職責範圍內的異常 : 鎖搶不到 (可能上次執行掛住) 、`run_once()` 拋出未預期例外 (例如 API 完全無回應、程式錯誤). 兩者都必須發警報, 否則會在無人值守時靜默失敗數小時甚至數天都無人發現
- `telegram_alerts.send_alert` 本身已保證不拋例外 (見既有實作), 所以 `scheduler.py` 不需要再包一層防護

## 測試 (testing)

`tests/test_paper_trading_scheduler.py` :

- 鎖可取得時, `run_scheduled` 會呼叫 `run_once.run_once()` 一次並回傳其結果 (mock `run_once.run_once`)
- 鎖已被其他 process 持有時 (測試中先用另一個檔案控 (file descriptor) 對同一個鎖檔取得 `flock`), `run_scheduled` 拋出 `SchedulerLockedError`, 且 `run_once.run_once` 未被呼叫
- `main()` 在 `SchedulerLockedError` 情況下, 呼叫了 `telegram_alerts.send_alert` 且 exit code 為 0
- `main()` 在 `run_once()` 拋出例外的情況下, 呼叫了 `telegram_alerts.send_alert` 且訊息包含錯誤內容, exit code 為 1
- `main()` 在正常完成的情況下, 不呼叫 `telegram_alerts.send_alert`, exit code 為 0
- 所有測試以 `tmp_path` fixture 提供鎖檔路徑, 不觸碰真正的 `logs/scheduler.lock`; `telegram_alerts.send_alert` 全程 mock, 不對外發真實請求

## 部署 (deployment)

實作完成並跑過 `pytest` 後, 新增以下 crontab 條目 (由 Claude 直接執行 `crontab` 指令加入, 使用者已核准) :

```
0 0,4,8,12,16,20 * * * cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 scheduler.py >> logs/cron.log 2>&1
```

加入前會先用手動執行 (`python3 scheduler.py`) 驗證一次成功路徑, 確認無誤後才寫入 crontab.
