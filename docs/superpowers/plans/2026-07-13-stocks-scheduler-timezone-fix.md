# 美股排程時區可靠性修復 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 `scheduler_stocks.py` 與 `monitor_stocks.py` 不再依賴這台伺服器上不可靠的 cron 時區/星期欄位解讀, 改由 Python 內部用 `zoneinfo` 判斷真正該不該動作。

**Architecture:** Crontab 兩支腳本都改成每 15 分鐘觸發一次、不限星期; 各自的 `main()` 在真正動作前先用注入的美東時間做窗口判斷, `scheduler_stocks.py` 額外查 `run_log_stocks.jsonl` 最後一筆紀錄防止同一天重複執行, `monitor_stocks.py` 用「昨天日期天然不重複」的特性防止重複發送, 不新增任何狀態檔案。

**Tech Stack:** Python 3.12, `zoneinfo` (stdlib), `pytest` + `monkeypatch`/`tmp_path`。

**規格文件:** [docs/superpowers/specs/2026-07-13-phase3-stocks-scheduler-timezone-fix-design.md](../specs/2026-07-13-phase3-stocks-scheduler-timezone-fix-design.md)

## Global Constraints

- 不新增任何狀態檔案。
- DST (daylight saving time, 夏令時) 交給 `zoneinfo("America/New_York")` 處理, 不手動計算時區偏移或維護轉換日期表。
- 不修改加密貨幣側 `scheduler.py` / `monitor.py` 與其 crontab。
- 不查明 `CRON_TZ` 在此伺服器失效的根本原因, 純粹繞開。
- 不處理美股行事曆「提早收盤日」的精確收盤時間, 沿用固定 16:00 ET 收盤 + 緩衝的既有精度。
- Crontab 兩行皆改為 `*/15 * * * *` (每 15 分鐘, 不限星期)。
- `scheduler_stocks.py` 目標窗口: 美東 `[16:35, 17:35)`。
- `monitor_stocks.py` 目標窗口: 美東 `[07:45, 08:00)`。
- 新函式一律以明確參數 (`now_eastern`) 注入時間, 不在核心邏輯內直接呼叫 `datetime.now()` (與既有 `risk_agent.check_data_staleness(current_time=...)` 的慣例一致), 以維持既有測試風格 (mock/合成資料, 不碰真實時間或網路)。
- 變數與函式命名一律全名, 不用縮寫 (repo CLAUDE.md 規則)。

---

## Task 1: `scheduler_stocks.py` — 目標窗口與去重防護

**Files:**
- Modify: `04_paper_trading/scheduler_stocks.py`
- Test: `tests/test_scheduler_stocks.py`

**Interfaces:**
- Consumes: 既有 `run_once_stocks.US_EASTERN_TIMEZONE` (`ZoneInfo` 物件)、`run_once_stocks.LOG_FILE_PATH` (字串路徑)、既有 `run_scheduled(lock_file_path: str) -> dict`、`SchedulerLockedError`
- Produces: `_is_within_target_window(now_eastern: datetime) -> bool`、`_has_already_run_today(log_file_path: str, today_eastern: str) -> bool`、`_should_run_now(now_eastern: datetime, log_file_path: str) -> bool`、`main(now_eastern: datetime | None = None) -> None` (簽名變更, 新增可選參數)

與 Task 2 (`monitor_stocks.py`) 互相獨立, 無共用介面, 可平行進行。

- [ ] **Step 1: 寫 `_is_within_target_window` 的失敗測試**

在 `tests/test_scheduler_stocks.py` 檔案開頭的 `import fcntl` 後面加一行 `from datetime import datetime`(與既有 `import fcntl` 同屬 stdlib import 群組, 維持 stdlib/第三方/本地三段分組的既有慣例), 變成:

```python
import fcntl
from datetime import datetime

import pytest

import scheduler_stocks
```

並在檔案結尾新增:

```python
def test_is_within_target_window_before_start_returns_false():
    now_eastern = datetime(2026, 7, 13, 16, 34, 59)

    assert scheduler_stocks._is_within_target_window(now_eastern) is False


def test_is_within_target_window_at_start_returns_true():
    now_eastern = datetime(2026, 7, 13, 16, 35, 0)

    assert scheduler_stocks._is_within_target_window(now_eastern) is True


def test_is_within_target_window_inside_returns_true():
    now_eastern = datetime(2026, 7, 13, 17, 0, 0)

    assert scheduler_stocks._is_within_target_window(now_eastern) is True


def test_is_within_target_window_at_end_returns_false():
    now_eastern = datetime(2026, 7, 13, 17, 35, 0)

    assert scheduler_stocks._is_within_target_window(now_eastern) is False


def test_is_within_target_window_after_end_returns_false():
    now_eastern = datetime(2026, 7, 13, 18, 0, 0)

    assert scheduler_stocks._is_within_target_window(now_eastern) is False
```

- [ ] **Step 2: 執行測試, 確認失敗**

Run: `cd 04_paper_trading && python3 -m pytest ../tests/test_scheduler_stocks.py -k target_window -v`
Expected: FAIL, `AttributeError: module 'scheduler_stocks' has no attribute '_is_within_target_window'`

- [ ] **Step 3: 實作 `_is_within_target_window`**

修改 `04_paper_trading/scheduler_stocks.py` 開頭的 import 區塊, 把:

```python
import fcntl
import os
import sys
import traceback
```

改成:

```python
import fcntl
import json
import os
import sys
import traceback
from datetime import datetime, time
```

在 `NOTIFY_RUN_SUMMARY = True` 那行之後、`class SchedulerLockedError` 之前, 新增:

```python
TARGET_WINDOW_START_EASTERN = time(16, 35)
TARGET_WINDOW_END_EASTERN = time(17, 35)


def _is_within_target_window(now_eastern: datetime) -> bool:
    """判斷現在美東時間是否落在收盤後目標執行窗口 [16:35, 17:35) 內"""
    return TARGET_WINDOW_START_EASTERN <= now_eastern.time() < TARGET_WINDOW_END_EASTERN
```

- [ ] **Step 4: 執行測試, 確認通過**

Run: `cd 04_paper_trading && python3 -m pytest ../tests/test_scheduler_stocks.py -k target_window -v`
Expected: 5 個測試全部 PASS

- [ ] **Step 5: 寫 `_has_already_run_today` 的失敗測試**

在 `tests/test_scheduler_stocks.py` 結尾新增:

```python
def test_has_already_run_today_returns_false_when_file_missing(tmp_path):
    log_file_path = str(tmp_path / "does_not_exist.jsonl")

    assert scheduler_stocks._has_already_run_today(log_file_path, "2026-07-13") is False


def test_has_already_run_today_returns_false_when_file_empty(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    open(log_file_path, "w", encoding="utf-8").close()

    assert scheduler_stocks._has_already_run_today(log_file_path, "2026-07-13") is False


def test_has_already_run_today_returns_false_when_last_line_malformed(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write('{"market_date_eastern": "2026-07-13"}\n')
        log_file.write("not valid json\n")

    assert scheduler_stocks._has_already_run_today(log_file_path, "2026-07-13") is False


def test_has_already_run_today_returns_true_when_last_record_is_today(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write('{"market_date_eastern": "2026-07-10"}\n')
        log_file.write('{"market_date_eastern": "2026-07-13"}\n')

    assert scheduler_stocks._has_already_run_today(log_file_path, "2026-07-13") is True


def test_has_already_run_today_returns_false_when_last_record_is_earlier_date(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write('{"market_date_eastern": "2026-07-10"}\n')

    assert scheduler_stocks._has_already_run_today(log_file_path, "2026-07-13") is False
```

- [ ] **Step 6: 執行測試, 確認失敗**

Run: `cd 04_paper_trading && python3 -m pytest ../tests/test_scheduler_stocks.py -k has_already_run_today -v`
Expected: FAIL, `AttributeError: module 'scheduler_stocks' has no attribute '_has_already_run_today'`

- [ ] **Step 7: 實作 `_has_already_run_today`**

在 `04_paper_trading/scheduler_stocks.py` 剛新增的 `_is_within_target_window` 函式後面接著新增:

```python
def _has_already_run_today(log_file_path: str, today_eastern: str) -> bool:
    """讀 run_log_stocks.jsonl 最後一行, 判斷今天(美東日期) 是否已經執行過一次"""
    if not os.path.exists(log_file_path):
        return False
    with open(log_file_path, "r", encoding="utf-8") as log_file:
        non_blank_lines = [line for line in log_file if line.strip()]
    if not non_blank_lines:
        return False
    try:
        last_record = json.loads(non_blank_lines[-1])
    except json.JSONDecodeError:
        return False
    if not isinstance(last_record, dict):
        return False
    return last_record.get("market_date_eastern") == today_eastern
```

- [ ] **Step 8: 執行測試, 確認通過**

Run: `cd 04_paper_trading && python3 -m pytest ../tests/test_scheduler_stocks.py -k has_already_run_today -v`
Expected: 5 個測試全部 PASS

- [ ] **Step 9: 寫 `_should_run_now` 與 `main()` 新行為的失敗測試, 並更新既有 5 個 `test_main_*` 測試**

在 `tests/test_scheduler_stocks.py` 結尾新增:

```python
def test_should_run_now_true_when_in_window_and_not_run_yet(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    now_eastern = datetime(2026, 7, 13, 17, 0, 0)

    assert scheduler_stocks._should_run_now(now_eastern, log_file_path) is True


def test_should_run_now_false_when_outside_window(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    now_eastern = datetime(2026, 7, 13, 12, 0, 0)

    assert scheduler_stocks._should_run_now(now_eastern, log_file_path) is False


def test_should_run_now_false_when_already_run_today(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write('{"market_date_eastern": "2026-07-13"}\n')
    now_eastern = datetime(2026, 7, 13, 17, 0, 0)

    assert scheduler_stocks._should_run_now(now_eastern, log_file_path) is False


def test_main_exits_early_without_calling_run_scheduled_when_should_run_now_is_false(monkeypatch):
    monkeypatch.setattr(scheduler_stocks, "_should_run_now", lambda now_eastern, log_file_path: False)
    was_called = {"called": False}
    monkeypatch.setattr(
        scheduler_stocks, "run_scheduled", lambda lock_file_path: was_called.update(called=True)
    )

    with pytest.raises(SystemExit) as exit_info:
        scheduler_stocks.main()

    assert exit_info.value.code == 0
    assert was_called["called"] is False
```

接著修改既有 5 個會呼叫 `scheduler_stocks.main()` 的測試, 各自在第一行 `monkeypatch.setattr` 之前加入一行, 讓它們略過新的窗口/去重判斷 (這些測試本來就不是在測窗口邏輯, 應該繼續驗證鎖定/告警/結束碼行為不變):

`test_main_skips_summary_when_market_closed`、`test_main_sends_summary_alert_and_exits_zero_when_market_open`、`test_main_sends_alert_and_exits_zero_when_locked`、`test_main_sends_alert_and_exits_one_when_run_once_raises`、`test_main_does_not_send_summary_when_notify_disabled` 這 5 個函式, 都在函式的第一行加上:

```python
    monkeypatch.setattr(scheduler_stocks, "_should_run_now", lambda now_eastern, log_file_path: True)
```

例如 `test_main_skips_summary_when_market_closed` 改成:

```python
def test_main_skips_summary_when_market_closed(monkeypatch):
    monkeypatch.setattr(scheduler_stocks, "_should_run_now", lambda now_eastern, log_file_path: True)
    fake_record = {"symbols": {}, "market_open": False}
    monkeypatch.setattr(scheduler_stocks, "run_scheduled", lambda lock_file_path: fake_record)
    alerts = []
    monkeypatch.setattr(
        scheduler_stocks.telegram_alerts, "send_alert", lambda message: alerts.append(message)
    )

    with pytest.raises(SystemExit) as exit_info:
        scheduler_stocks.main()

    assert exit_info.value.code == 0
    assert alerts == []
```

其餘 4 個測試比照辦理, 只在函式開頭加那一行 `monkeypatch.setattr(scheduler_stocks, "_should_run_now", ...)`, 其餘內容不動。

- [ ] **Step 10: 執行完整測試檔, 確認新測試失敗、舊測試因屬性不存在而失敗**

Run: `cd 04_paper_trading && python3 -m pytest ../tests/test_scheduler_stocks.py -v`
Expected: 新增的 4 個測試 FAIL (`_should_run_now` 不存在); 5 個修改過的 `test_main_*` 也 FAIL (`monkeypatch.setattr` 對不存在的屬性報錯)

- [ ] **Step 11: 實作 `_should_run_now` 並接進 `main()`**

在 `04_paper_trading/scheduler_stocks.py` 的 `_has_already_run_today` 函式後面接著新增:

```python
def _should_run_now(now_eastern: datetime, log_file_path: str) -> bool:
    """兩個條件皆成立才需要真的執行: 現在落在目標窗口內, 且今天(美東日期) 還沒執行過"""
    if not _is_within_target_window(now_eastern):
        return False
    today_eastern = now_eastern.date().isoformat()
    return not _has_already_run_today(log_file_path, today_eastern)
```

把 `main()` 從:

```python
def main() -> None:
    try:
        record = run_scheduled(SCHEDULER_LOCK_PATH)
```

改成:

```python
def main(now_eastern: datetime | None = None) -> None:
    now_eastern = now_eastern if now_eastern is not None else datetime.now(run_once_stocks.US_EASTERN_TIMEZONE)
    if not _should_run_now(now_eastern, run_once_stocks.LOG_FILE_PATH):
        sys.exit(0)
    try:
        record = run_scheduled(SCHEDULER_LOCK_PATH)
```

`main()` 其餘內容 (except 區塊、market_open 檢查、Telegram 摘要) 不變。

同時把檔案開頭的 docstring 第 2-4 行:

```
Phase 3 紙上交易 (paper trading) 美股排程器 (scheduler): 包住 run_once_stocks.run_once() 的排程
安全網, 提供防重疊執行的鎖(lock) 與失敗告警, 讓 crontab 可以無人值守地在每個美股交易日收盤後觸發一次.
非交易日(run_once_stocks 回報 market_open=False) 不發送 Telegram 摘要, 避免週末/假日連續洗版
```

改成:

```
Phase 3 紙上交易 (paper trading) 美股排程器 (scheduler): 包住 run_once_stocks.run_once() 的排程
安全網, 提供防重疊執行的鎖(lock) 與失敗告警. crontab 每 15 分鐘觸發一次, 由 _should_run_now 內部
用美東時間判斷是否落在收盤後目標窗口且今天尚未執行, 不依賴 cron 本身的時區/星期欄位解讀(該解讀在
本機不可靠, 見 docs/superpowers/specs/2026-07-13-phase3-stocks-scheduler-timezone-fix-design.md).
非交易日(run_once_stocks 回報 market_open=False) 不發送 Telegram 摘要, 避免週末/假日連續洗版
```

- [ ] **Step 12: 執行完整測試檔, 確認全部通過**

Run: `cd 04_paper_trading && python3 -m pytest ../tests/test_scheduler_stocks.py -v`
Expected: 全部 PASS (原有 10 個 + 新增 14 個 [Step 1 五個 + Step 5 五個 + Step 9 四個] = 24 個測試)

- [ ] **Step 13: Commit**

```bash
git add 04_paper_trading/scheduler_stocks.py tests/test_scheduler_stocks.py
git commit -m "fix: gate scheduler_stocks.py run on injected Eastern time, not cron's timezone

Adds a post-close target window check and a same-day dedup check
against run_log_stocks.jsonl, both driven by an explicit now_eastern
parameter instead of trusting cron's CRON_TZ/weekday handling.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
git push
```

---

## Task 2: `monitor_stocks.py` — 目標窗口與交易日判定修正

**Files:**
- Modify: `04_paper_trading/monitor_stocks.py`
- Test: `tests/test_monitor_stocks.py`

**Interfaces:**
- Consumes: 既有 `US_EASTERN_TIMEZONE`、`LOG_FILE_PATH`、`_load_records_for_date(log_file_path: str, target_date: date) -> list[dict]`、`_format_daily_report(records: list[dict], target_date: date) -> str`
- Produces: `_is_within_target_window(now_eastern: datetime) -> bool`、`main(now_eastern: datetime | None = None) -> None` (簽名變更, 新增可選參數)

與 Task 1 互相獨立, 無共用介面, 可平行進行。

- [ ] **Step 1: 寫 `_is_within_target_window` 的失敗測試**

在 `tests/test_monitor_stocks.py` 檔案開頭的 `from datetime import date, datetime, timedelta` 改成 `from datetime import date, datetime, time, timedelta`, 並在檔案結尾新增:

```python
def test_is_within_target_window_before_start_returns_false():
    now_eastern = datetime(2026, 7, 13, 7, 44, 59)

    assert monitor_stocks._is_within_target_window(now_eastern) is False


def test_is_within_target_window_at_start_returns_true():
    now_eastern = datetime(2026, 7, 13, 7, 45, 0)

    assert monitor_stocks._is_within_target_window(now_eastern) is True


def test_is_within_target_window_inside_returns_true():
    now_eastern = datetime(2026, 7, 13, 7, 50, 0)

    assert monitor_stocks._is_within_target_window(now_eastern) is True


def test_is_within_target_window_at_end_returns_false():
    now_eastern = datetime(2026, 7, 13, 8, 0, 0)

    assert monitor_stocks._is_within_target_window(now_eastern) is False


def test_is_within_target_window_after_end_returns_false():
    now_eastern = datetime(2026, 7, 13, 9, 0, 0)

    assert monitor_stocks._is_within_target_window(now_eastern) is False
```

- [ ] **Step 2: 執行測試, 確認失敗**

Run: `cd 04_paper_trading && python3 -m pytest ../tests/test_monitor_stocks.py -k target_window -v`
Expected: FAIL, `AttributeError: module 'monitor_stocks' has no attribute '_is_within_target_window'`

- [ ] **Step 3: 實作 `_is_within_target_window`**

修改 `04_paper_trading/monitor_stocks.py` 開頭的 import, 把:

```python
import json
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
```

改成:

```python
import json
import os
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
```

在 `EXPECTED_RUNS_PER_DAY = 1` 那行之後、`def _load_records_for_date` 之前, 新增:

```python
TARGET_WINDOW_START_EASTERN = time(7, 45)
TARGET_WINDOW_END_EASTERN = time(8, 0)


def _is_within_target_window(now_eastern: datetime) -> bool:
    """判斷現在美東時間是否落在開盤前目標執行窗口 [07:45, 08:00) 內"""
    return TARGET_WINDOW_START_EASTERN <= now_eastern.time() < TARGET_WINDOW_END_EASTERN
```

- [ ] **Step 4: 執行測試, 確認通過**

Run: `cd 04_paper_trading && python3 -m pytest ../tests/test_monitor_stocks.py -k target_window -v`
Expected: 5 個測試全部 PASS

- [ ] **Step 5: 改寫 `main()` 的既有測試並新增兩個跳過路徑的測試**

把 `tests/test_monitor_stocks.py` 裡的 `test_main_loads_formats_and_sends_report_for_previous_eastern_trading_day` 整個函式替換成:

```python
def test_main_loads_formats_and_sends_report_for_previous_eastern_trading_day(monkeypatch):
    captured = {}

    def _fake_load_records_for_date(log_file_path, target_date):
        captured["log_file_path"] = log_file_path
        captured["target_date"] = target_date
        return [{"marker": "fake_record", "market_open": True}]

    def _fake_format_daily_report(records, target_date):
        captured["records"] = records
        captured["format_target_date"] = target_date
        return "格式化後的報告文字"

    sent_messages = []
    monkeypatch.setattr(monitor_stocks, "_load_records_for_date", _fake_load_records_for_date)
    monkeypatch.setattr(monitor_stocks, "_format_daily_report", _fake_format_daily_report)
    monkeypatch.setattr(
        monitor_stocks.telegram_alerts, "send_alert", lambda message: sent_messages.append(message)
    )

    now_eastern = datetime(2026, 7, 11, 7, 50, 0)
    monitor_stocks.main(now_eastern=now_eastern)

    expected_target_date = (now_eastern - timedelta(days=1)).date()
    assert captured["target_date"] == expected_target_date
    assert captured["format_target_date"] == expected_target_date
    assert captured["records"] == [{"marker": "fake_record", "market_open": True}]
    assert sent_messages == ["格式化後的報告文字"]


def test_main_skips_when_outside_target_window(monkeypatch):
    was_called = {"called": False}
    monkeypatch.setattr(
        monitor_stocks, "_load_records_for_date",
        lambda log_file_path, target_date: was_called.update(called=True),
    )
    sent_messages = []
    monkeypatch.setattr(
        monitor_stocks.telegram_alerts, "send_alert", lambda message: sent_messages.append(message)
    )

    now_eastern = datetime(2026, 7, 11, 12, 0, 0)
    monitor_stocks.main(now_eastern=now_eastern)

    assert was_called["called"] is False
    assert sent_messages == []


def test_main_skips_when_previous_day_was_not_a_trading_day(monkeypatch):
    monkeypatch.setattr(
        monitor_stocks, "_load_records_for_date",
        lambda log_file_path, target_date: [{"market_date_eastern": str(target_date), "market_open": False}],
    )
    sent_messages = []
    monkeypatch.setattr(
        monitor_stocks.telegram_alerts, "send_alert", lambda message: sent_messages.append(message)
    )

    now_eastern = datetime(2026, 7, 13, 7, 50, 0)
    monitor_stocks.main(now_eastern=now_eastern)

    assert sent_messages == []
```

- [ ] **Step 6: 執行測試, 確認失敗**

Run: `cd 04_paper_trading && python3 -m pytest ../tests/test_monitor_stocks.py -k main -v`
Expected: FAIL — `monitor_stocks.main()` 目前不接受 `now_eastern` 關鍵字參數 (`TypeError`), 且沒有窗口/交易日判斷邏輯

- [ ] **Step 7: 重寫 `main()`**

把 `04_paper_trading/monitor_stocks.py` 的:

```python
def main() -> None:
    target_date = (datetime.now(US_EASTERN_TIMEZONE) - timedelta(days=1)).date()
    records = _load_records_for_date(LOG_FILE_PATH, target_date)
    report = _format_daily_report(records, target_date)
    telegram_alerts.send_alert(report)
    print(f"美股每日報告已發送 ({target_date.isoformat()}), 涵蓋 {len(records)} 筆執行紀錄")
```

改成:

```python
def main(now_eastern: datetime | None = None) -> None:
    now_eastern = now_eastern if now_eastern is not None else datetime.now(US_EASTERN_TIMEZONE)
    if not _is_within_target_window(now_eastern):
        return
    target_date = (now_eastern - timedelta(days=1)).date()
    records = _load_records_for_date(LOG_FILE_PATH, target_date)
    if not any(record.get("market_open") for record in records):
        return
    report = _format_daily_report(records, target_date)
    telegram_alerts.send_alert(report)
    print(f"美股每日報告已發送 ({target_date.isoformat()}), 涵蓋 {len(records)} 筆執行紀錄")
```

同時把檔案開頭 docstring 第 2-3 行:

```
Phase 3 紙上交易 (paper trading) 美股每日報告 (monitor): 讀取 run_log_stocks.jsonl 中前一個美東交易日
的執行紀錄, 彙總成每日報告透過 Telegram 發送. 由獨立 crontab 於次日美股開盤前觸發.
```

改成:

```
Phase 3 紙上交易 (paper trading) 美股每日報告 (monitor): 讀取 run_log_stocks.jsonl 中前一個美東交易日
的執行紀錄, 彙總成每日報告透過 Telegram 發送. crontab 每 15 分鐘觸發一次, 由 main() 內部用美東時間判斷
是否落在開盤前目標窗口, 且「昨天」是否真的有交易紀錄(market_open=True), 兩者皆成立才發送, 不依賴 cron
本身的時區/星期欄位解讀, 也不需要額外狀態檔做去重(見 docs/superpowers/specs/2026-07-13-phase3-stocks-
scheduler-timezone-fix-design.md 的「去重設計」段落).
```

- [ ] **Step 8: 執行完整測試檔, 確認全部通過**

Run: `cd 04_paper_trading && python3 -m pytest ../tests/test_monitor_stocks.py -v`
Expected: 全部 PASS (原有 8 個, 其中 1 個被改寫 + 新增 7 個 [Step 1 五個 + Step 5 新增兩個] = 15 個測試)

- [ ] **Step 9: Commit**

```bash
git add 04_paper_trading/monitor_stocks.py tests/test_monitor_stocks.py
git commit -m "fix: gate monitor_stocks.py on injected Eastern time and verified prior trading day

Adds a pre-open target window check and replaces the blind
'yesterday minus 1 day' date math with a check that yesterday
actually has a market_open=True record, so Monday no longer looks
for Sunday and Friday's summary is no longer silently dropped.
Dedup is free: each calendar day's 'yesterday' is asked about at
most once, so no new state file is needed.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
git push
```

---

## Task 3: Crontab 更新與驗證

**Files:**
- 無程式碼變更 (伺服器設定, 不在版控範圍內)

**Interfaces:**
- Consumes: Task 1、Task 2 完成且已測試通過 (兩支腳本都已經能正確處理高頻觸發)

- [ ] **Step 1: 備份目前 crontab**

```bash
crontab -l > 04_paper_trading/logs/crontab-backup-before-tz-fix.txt
cat 04_paper_trading/logs/crontab-backup-before-tz-fix.txt
```

Expected: 印出目前包含 `CRON_TZ=America/New_York` 那 4 行美股/加密貨幣排程的完整內容, 與備份檔一致。

- [ ] **Step 2: 套用新 crontab (不落地額外檔案, 直接用 heredoc 覆蓋)**

```bash
crontab - <<'EOF'
0 0,4,8,12,16,20 * * * cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 scheduler.py >> logs/cron.log 2>&1
0 0 * * * cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 monitor.py >> logs/cron.log 2>&1

*/15 * * * * cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 scheduler_stocks.py >> logs/cron.log 2>&1
*/15 * * * * cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 monitor_stocks.py >> logs/cron.log 2>&1
EOF
crontab -l
```

前兩行 (加密貨幣) 與 Step 1 備份的內容逐字相同, 只是拿掉中間的 `CRON_TZ=America/New_York` 那行, 並把美股兩行改成 `*/15 * * * *`。

Expected: `crontab -l` 印出的內容與上面 heredoc 一致, 不再有 `CRON_TZ` 那一行。

- [ ] **Step 3: 零副作用的乾跑檢查, 確認現在這一刻兩支腳本會不會誤動作**

```bash
cd 04_paper_trading && python3 -c "
from datetime import datetime
import scheduler_stocks, monitor_stocks

now_scheduler = datetime.now(scheduler_stocks.run_once_stocks.US_EASTERN_TIMEZONE)
now_monitor = datetime.now(monitor_stocks.US_EASTERN_TIMEZONE)
print('scheduler_stocks 現在會不會進入判斷:', scheduler_stocks._is_within_target_window(now_scheduler), now_scheduler)
print('monitor_stocks 現在會不會進入判斷:', monitor_stocks._is_within_target_window(now_monitor), now_monitor)
"
```

Expected: 印出兩個布林值與對應的美東時間, 純讀取判斷, 不會觸發下單或發送 Telegram, 用來確認函式在真實環境下算出的美東時間是合理的 (跟你手錶對得上)。

- [ ] **Step 4: 記錄後續人工驗證項目 (無法在這次會話內同步等到, 留給下一個美股交易日自然驗證)**

不是 pytest 步驟, 是給人看的檢查清單, 建議下一個美東收盤後 (16:35-17:35 ET) 與次日開盤前 (07:45-08:00 ET) 各回來看一次:

```bash
tail -5 04_paper_trading/logs/run_log_stocks.jsonl
tail -30 04_paper_trading/logs/cron.log
```

確認: (a) `run_log_stocks.jsonl` 當天只新增一筆紀錄, 不是好幾筆重複的; (b) `cron.log` 沒有被大量空 tick 洗版 (應該仍然只在真正執行或出錯時才有輸出); (c) Telegram 有收到當天的執行摘要與隔天早上的每日報告, 時間點看起來接近美東收盤後/開盤前, 不是台北/香港時間的下午 4 點半。

No commit for this task (crontab is not version-controlled); the backup file in `04_paper_trading/logs/` is already gitignored.
