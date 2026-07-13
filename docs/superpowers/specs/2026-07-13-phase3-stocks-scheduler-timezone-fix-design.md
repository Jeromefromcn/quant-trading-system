# Phase 3 紙上交易 (paper trading) 美股排程時區可靠性修復設計文件

日期: 2026-07-13
狀態: 已核准 (approved), 待寫實作計劃 (implementation plan)

## 背景 (background)

2026-07-13 (週一) 收到 Telegram 警報「[美股] 數據異常保護觸發, 暫停信號生成: VOO, QQQ」。根因調查 (詳見對話記錄, 未另外寫成文件) 確認:

- Crontab 用 `CRON_TZ=America/New_York` 搭配 `35 16 * * 1-5` 讓 `scheduler_stocks.py` 在美東收盤後 35 分鐘 (16:35 ET) 執行, 但這台伺服器 (`Asia/Hong_Kong`, UTC+8) 的 cron (`cron 3.0pl1-184ubuntu2`) 並未正確套用 `CRON_TZ`, 實際仍以伺服器本地時區解讀時間欄位。這使得排程在美股開盤前 (美東凌晨 4:35) 就執行, 平常工作日抓到的仍是前一天收盤價 (间隔約 12.5 小時, 在 1.5 天的過期門檻內, 不會觸發保護), 但跨週末時間隔拉大到超過 36 小時, 觸發 `risk_agent.check_data_staleness` 的假警報——數據抓取本身沒有失敗, 只是排程執行的時間點不對。
- 同一份 crontab 下的 `monitor_stocks.py` (`0 8 * * 1-5`, 意圖美東 08:00 執行) 也受同樣問題影響, 且額外曝露一個獨立、與 CRON_TZ 無關的既有 bug: [monitor_stocks.py:122](../../../04_paper_trading/monitor_stocks.py#L122) 固定用「今天 − 1 天」算前一交易日, 沒有跳過週末, 導致週一的報告永遠找不到紀錄 (查的是週日), 而週五的交易結果從未被回報過。
- 若單純把 cron 的時、分欄位改成「反推出的 HKT 對應時間」, 會再踩到一個星期欄位陷阱: 美東週五收盤時間換算成伺服器 HKT 時間落在**週六凌晨**, 若 cron 星期欄位仍寫 `1-5` 會把週五收盤這次執行整個排除掉。
- 原始設計文件 [2026-07-10-phase3-us-stocks-paper-trading-design.md](2026-07-10-phase3-us-stocks-paper-trading-design.md) 的排程段落已經預見「若系統 cron 不支援 CRON_TZ」的風險, 並記錄為已知限制待後續處理——本文件就是那個後續處理。
- 加密貨幣側 `scheduler.py` / `monitor.py` 不受影響: 24 小時市場用固定 UTC 時間點觸發, 原設計文件已明確排除「是否收盤 / 是否交易日」這類判斷, 不在本次範圍內。

## 目標與範圍 (goal and scope)

**目標**: 讓美股排程完全不依賴這台伺服器上「cron 對時區/星期欄位的解讀是否正確」這個已證實不可靠的前提, 由 Python 內部用 `zoneinfo("America/New_York")` (系統 tzdata 套件維護 DST 規則, 不需要每年人工調整) 判斷真正該不該動作, cron 只負責高頻率地「叫醒」腳本。

**本次範圍內**:

- `04_paper_trading/scheduler_stocks.py`: 新增目標時間窗口判斷與「今天是否已執行過」的去重檢查
- `04_paper_trading/monitor_stocks.py`: 新增目標時間窗口判斷; 修正「前一交易日」的判定邏輯 (獨立於 CRON_TZ 問題的既有 bug)
- Crontab: 拿掉 `CRON_TZ` 區塊與 `1-5` 星期限制, 改為兩行皆每 15 分鐘觸發、不限星期

**明確排除**:

- 不查明這台機器上 `CRON_TZ` 具體為何失效, 純粹繞開, 不修 cron 本身
- 不變動加密貨幣側 `scheduler.py` / `monitor.py` 與其 crontab
- 不處理美股行事曆中「提早收盤日」(例如感恩節隔天) 的精確收盤時間, 沿用原設計「固定 16:00 收盤 + 緩衝」的精度, 沒有變得更差
- 不新增任何狀態檔案 (見下方「元件」段落的去重設計)

## 元件 (components)

### `scheduler_stocks.py` 修改

新增兩個模組層級函式 (純函式, 方便測試), 在 `main()` 呼叫既有 `run_scheduled(...)` 之前執行, 兩者皆通過才繼續, 其餘既有邏輯 (鎖、`run_once_stocks.run_once()`、失敗告警) 不變:

- `_is_within_target_window(now_eastern: datetime) -> bool`: 檢查 `now_eastern.time()` 是否落在 `[16:35, 17:35)` ET。窗口 60 分鐘寬, 每 15 分鐘一次的觸發至少有 4 次機會落在窗口內, 對單次系統延遲有容錯空間。
- `_has_already_run_today(log_file_path: str, today_eastern: str) -> bool`: 讀 `run_log_stocks.jsonl` 最後一行 (檔案不存在、為空、或最後一行 JSON 解析失敗皆回傳 `False`, 與 `monitor_stocks._load_records_for_date` 對格式錯誤的容錯原則一致), 比對其 `market_date_eastern` 是否等於 `today_eastern`。

兩個檢查皆不通過時, `main()` 直接 `sys.exit(0)`, 不印任何內容, 不觸碰鎖檔, 不呼叫 `run_once_stocks.run_once()`。

**這一步是防重複下單的關鍵, 不只是效率優化**: 高頻輪詢下, 目標窗口內可能被觸發好幾次; LOO (limit-on-open) 委託在次日開盤前不會改變 `current_share_balance`, 若沒有這層去重, `risk_agent.review_portfolio` 對同一個目標倉位會重複產生 `OrderEvent`。

**刻意不做的事**: 不額外判斷「今天星期幾」——手動反推時區/星期正是這次誤判的根因。是否為交易日完全交給 `run_once_stocks.py` 既有的 Alpaca 交易日曆查詢 ([run_once_stocks.py:77-81](../../../04_paper_trading/run_once_stocks.py#L77-L81)), 這是唯一可信來源, 已正確處理國定假日, 且是已測試過的既有路徑。窗口不配合星期限制意味著週末每天也會被戳一下, 成本是一次已經很輕量的日曆查詢, 可接受。

### `monitor_stocks.py` 修改

- 新增 `_is_within_target_window(now_eastern: datetime) -> bool`: 檢查是否落在 `[07:45, 08:00)` ET。**這個窗口只有 15 分鐘寬**(對齊單一次 `*/15` 觸發點), 比 `scheduler_stocks.py` 窄, 原因見下方「去重設計」。
- `main()` 邏輯修改: 通過窗口檢查後, 算出 `yesterday_eastern = (now_eastern - timedelta(days=1)).date()`, 呼叫既有 `_load_records_for_date(LOG_FILE_PATH, yesterday_eastern)`。若回傳的紀錄裡沒有任何一筆 `market_open == True`(代表昨天不是真正的交易日, 或還沒有任何紀錄), 直接跳過, **不發送 Telegram, 也不印「無執行紀錄」**。有真正交易日紀錄才呼叫既有 `_format_daily_report(...)` 並發送。
- `_load_records_for_date` 與 `_format_daily_report` 兩個既有函式簽名與內部邏輯不變, 只有 `main()` 的日期計算方式與新增的前置檢查改變。

**去重設計 (不新增狀態檔)**: 「昨天」這個日期每個日曆天都不同, 且永遠不會被重複問到——週六問「週五」、週日問「週六」、週一問「週日」, 彼此互斥。週五的彙總只會在週六被問到一次, 週日、週一問到的是非交易日, 安靜跳過, 不會重問到週五。跨日曆天天然去重, 不需要記錄「是否已發送」。唯一要付出的代價是同一天內不能容忍多次觸發都落在窗口內 (會重複發送), 所以窗口必須縮到剛好對齊一次輪詢間隔 (15 分鐘)——換來的是完全不需要新檔案。這個取捨只套用在 `monitor_stocks.py`(彙總報告, 非交易動作, 錯過一次頂多是晚一天才看到消息); `scheduler_stocks.py` 因為已經需要讀 `run_log_stocks.jsonl` 做「今天是否已執行」檢查, 保留較寬的窗口不需要額外成本, 兩者取捨不同是刻意的, 不是不一致。

**額外的副作用 (非目標, 但值得記錄)**: 修好之後, 週末/假日 `monitor_stocks.py` 會完全靜默, 週五的交易結果會在週六早上第一次被回報 (以前從未被回報過)。

### Crontab 修改

移除整個 `CRON_TZ=America/New_York` 區塊, 兩行改為不限星期、每 15 分鐘觸發; 加密貨幣兩行不動:

```
0 0,4,8,12,16,20 * * * cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 scheduler.py >> logs/cron.log 2>&1
0 0 * * * cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 monitor.py >> logs/cron.log 2>&1

*/15 * * * * cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 scheduler_stocks.py >> logs/cron.log 2>&1
*/15 * * * * cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 monitor_stocks.py >> logs/cron.log 2>&1
```

## 資料流 (data flow)

**`scheduler_stocks.py` 每次被 cron 觸發**:

1. 算出美東現在時間, `_is_within_target_window` 檢查是否在 `[16:35, 17:35)` ET 內。否 → 結束
2. 算出美東今天日期, `_has_already_run_today` 檢查 `run_log_stocks.jsonl` 最後一筆紀錄。是 → 結束
3. 兩者皆否 (窗口內且今天尚未執行) → 照既有邏輯呼叫 `run_scheduled(...)` (鎖 → `run_once_stocks.run_once()` → 依結果決定要不要發 Telegram 摘要)

**`monitor_stocks.py` 每次被 cron 觸發**:

1. 算出美東現在時間, `_is_within_target_window` 檢查是否在 `[07:45, 08:00)` ET 內。否 → 結束, 不印任何內容
2. 算出美東昨天日期, 讀 `run_log_stocks.jsonl` 篩出該日期的紀錄。沒有任何一筆 `market_open == True` → 結束, 不發送, 不印任何內容
3. 有 → 組成報告, 發送 Telegram, 印出完成訊息 (與現有行為相同)

## 錯誤處理 (error handling)

- **執行到一半當機** (例如已送出 VOO 委託, 寫 log 前中斷): 15 分鐘後下一個 tick 可能重跑導致部分重複下單。這個風險在原本「一天只觸發一次」的設計下不存在, 是高頻輪詢引入的新邊界情況, 但發生機率低 (當機時間點要剛好落在極窄區間內), 且既有例外處理仍會發 Telegram 警報讓使用者知情。這次不特別加防護 (例如下單前二次查詢 Alpaca 未結委託), 記錄在此供之後參考, 不是本次要解決的問題
- **整個目標窗口都沒有 tick 命中** (伺服器當機/斷網): 當天不執行/不發報告, 與現行失效模式相同, 不是變差
- **`monitor_stocks.py` 窗口內被觸發超過一次**: 會重複發送同一份報告 (見上方去重設計的代價), 視為可接受風險
- 兩個新窗口的時間點無交集 (`scheduler_stocks.py` 16:35-17:35, `monitor_stocks.py` 07:45-08:00), 不會互相干擾; `monitor_stocks.py` 讀取的是前一個交易日已經穩定寫入多小時的 log, 不存在讀到寫一半資料的競態問題

## 測試與檔案結構 (testing and file layout)

沿用既有測試風格 (`tests/test_scheduler_stocks.py`、`tests/test_paper_trading_monitor.py` 已存在, 合成 (synthetic) 資料 mock, 不打真實網路):

- `_is_within_target_window`(兩個檔案各自的版本): 純函式單元測試, 覆蓋窗口前、窗口起點(含)、窗口內、窗口終點(不含)、窗口後
- `scheduler_stocks._has_already_run_today`: 覆蓋檔案不存在、檔案為空、最後一筆是今天、最後一筆是更早日期
- `scheduler_stocks.main()`: 覆蓋窗口外跳過、今天已執行跳過、兩者皆通過才呼叫 `run_scheduled`(既有測試已覆蓋 `run_scheduled` 本身, 不重複)
- `monitor_stocks.main()`: 覆蓋昨天無 `market_open=True` 紀錄時不發送、昨天有紀錄時正常組報告發送(既有 `_load_records_for_date` / `_format_daily_report` 測試不重複)

修改檔案 (無新增檔案):

```
04_paper_trading/
  scheduler_stocks.py    (修改: 新增窗口 + 去重檢查)
  monitor_stocks.py      (修改: 新增窗口檢查, 修正前一交易日邏輯)
tests/
  test_scheduler_stocks.py         (擴充)
  test_paper_trading_monitor.py    (擴充)
```

Crontab 修改為伺服器設定, 不在版控範圍內, 於實作驗收時人工更新。
