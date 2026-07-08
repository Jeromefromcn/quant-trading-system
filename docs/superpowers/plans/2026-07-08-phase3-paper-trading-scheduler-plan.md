# Phase 3 紙上交易 (paper trading) 排程器 (scheduler) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 `04_paper_trading/scheduler.py` 能包住 `run_once.run_once()`, 提供防重疊執行的鎖 (lock) 與失敗告警, 使加密貨幣紙上交易可在 crontab 每 4 小時無人值守觸發一次.

**Architecture:** `scheduler.py` 提供兩個函式 : `run_scheduled(lock_file_path)` 用 `fcntl.flock` 的非阻塞獨占鎖包住一次 `run_once.run_once()` 呼叫, 搶不到鎖就拋出自訂例外 `SchedulerLockedError`; `main()` 呼叫 `run_scheduled()` 並依 (正常完成 / 鎖搶不到 / 其他例外) 三種情況分流, 決定要不要發 Telegram 告警與最終 exit code. 沿用 `run_once.py` 既有的 `sys.path.insert` 手法, 不引入新的專案結構.

**Tech Stack:** Python 3, `fcntl` (POSIX 檔案鎖), `pytest` + `monkeypatch` (既有測試慣例), 既有 `telegram_alerts.send_alert`, 系統 `crontab`.

## Global Constraints

- 本切片只處理加密貨幣排程, 不做 Alpaca 美股整合或 `monitor.py` 每日彙總報告 (留給後續切片).
- 不使用 systemd timer 或其他排程機制, 沿用這台機器既有的 crontab 慣例.
- 排程觸發的 6 個固定 UTC 時間點: `0 0,4,8,12,16,20 * * *`.
- 鎖檔預設路徑 `04_paper_trading/logs/scheduler.lock`, 以模組層級常數定義, 測試時可覆寫.
- `run_scheduled()` 搶不到鎖時只拋出 `SchedulerLockedError`, 不自己發告警 : 告警一律交給 `main()` 統一處理 (單一職責, 方便測試以 mock 驗證).
- `run_once()` 內部已處理的異常 (資料抓取失敗、風控拒絕、熔斷、數據異常) 不在 `scheduler.py` 的職責範圍內, 不重複告警.
- `telegram_alerts.send_alert` 本身保證不拋例外, `scheduler.py` 不需要再包一層防護.
- 執行紀錄透過 crontab 導向 `04_paper_trading/logs/cron.log` (已被 `.gitignore` 的 `logs/` 規則排除).
- 不修改 `run_once.py` : 其 `run_once()` 函式簽名已可直接呼叫.

---

## File Structure

- Create: `04_paper_trading/scheduler.py` : 排程安全網本體 (鎖 + 告警分流), 唯一新檔案.
- Create: `tests/test_paper_trading_scheduler.py` : `scheduler.py` 的單元測試, 全程 mock, 不碰真正鎖檔或外部網路.
- Modify: 無其他既有檔案 (`run_once.py`, `telegram_alerts.py` 均不需改動).
- Modify: 系統 crontab (透過 `crontab` 指令, 非專案內檔案) : 部署步驟才會動到.

---

### Task 1: `run_scheduled()` 與 `SchedulerLockedError`

**Files:**
- Create: `04_paper_trading/scheduler.py`
- Test: `tests/test_paper_trading_scheduler.py`

**Interfaces:**
- Consumes: `run_once.run_once() -> dict` (既有函式, 見 `04_paper_trading/run_once.py:76`), `conftest.py` 已把 `04_paper_trading` 加入 `sys.path`, 測試可直接 `import scheduler`.
- Produces: `scheduler.SchedulerLockedError` (Exception 子類別), `scheduler.run_scheduled(lock_file_path: str) -> dict` : 供 Task 2 的 `main()` 呼叫.

- [ ] **Step 1: 建立 `04_paper_trading/scheduler.py` 骨架 (模組 docstring、imports、常數), 先不寫函式邏輯**

```python
"""
Phase 3 紙上交易 (paper trading) 排程器 (scheduler) : 包住 run_once.run_once() 的排程安全網,
提供防重疊執行的鎖 (lock) 與失敗告警, 讓 crontab 可以無人值守地每 4 小時觸發一次.
見設計文件 docs/superpowers/specs/2026-07-08-phase3-paper-trading-scheduler-design.md
用法: python3 scheduler.py
"""
import fcntl
import os
import sys
import traceback

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)

import run_once  # noqa: E402
import telegram_alerts  # noqa: E402

SCHEDULER_LOCK_PATH = os.path.join(_paper_trading_directory, "logs", "scheduler.lock")
```

- [ ] **Step 2: 寫失敗測試 : 鎖可取得時, `run_scheduled` 呼叫 `run_once.run_once()` 一次並回傳其結果**

Create `tests/test_paper_trading_scheduler.py`:

```python
"""scheduler.py 的排程安全網測試 : 鎖行為與告警分流全程 mock, 不碰真正鎖檔或外部網路"""
import fcntl
import os

import pytest

import scheduler


def test_run_scheduled_calls_run_once_when_lock_available(tmp_path, monkeypatch):
    lock_file_path = str(tmp_path / "scheduler.lock")
    call_count = {"n": 0}

    def _fake_run_once():
        call_count["n"] += 1
        return {"symbols": {}}

    monkeypatch.setattr(scheduler.run_once, "run_once", _fake_run_once)

    result = scheduler.run_scheduled(lock_file_path)

    assert call_count["n"] == 1
    assert result == {"symbols": {}}
```

- [ ] **Step 3: 執行測試確認失敗 (此時 `run_scheduled` 尚未定義)**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_scheduler.py -v`
Expected: FAIL : `AttributeError: module 'scheduler' has no attribute 'run_scheduled'`

- [ ] **Step 4: 實作 `SchedulerLockedError` 與 `run_scheduled()`, 讓 Step 2 測試通過**

Append to `04_paper_trading/scheduler.py`:

```python
class SchedulerLockedError(Exception):
    """上一次排程執行尚未結束 (鎖仍被持有), 本次應跳過, 不與上一次併發執行"""


def run_scheduled(lock_file_path: str) -> dict:
    """
    以 fcntl.flock(LOCK_EX | LOCK_NB) 對 lock_file_path 嘗試取得非阻塞的獨占鎖
    (exclusive lock, 非阻塞 non-blocking). 取得鎖時呼叫 run_once.run_once() 並回傳其結果;
    鎖隨本函式的檔案物件被釋放或 process 結束而釋放(crash 時核心也會自動釋放,
    不會留下無法清除的殘留鎖). 搶不到鎖時拋出 SchedulerLockedError, 不自己發告警
    (告警交給 main() 統一處理, 方便測試以 mock 驗證)
    """
    os.makedirs(os.path.dirname(lock_file_path), exist_ok=True)
    lock_file = open(lock_file_path, "w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        raise SchedulerLockedError(f"排程鎖 {lock_file_path} 已被持有, 上一次執行可能尚未結束")
    return run_once.run_once()
```

- [ ] **Step 5: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_scheduler.py -v`
Expected: PASS

- [ ] **Step 6: 寫失敗測試 : 鎖已被其他 process 持有時, `run_scheduled` 拋出 `SchedulerLockedError`, 且 `run_once.run_once` 未被呼叫**

Append to `tests/test_paper_trading_scheduler.py`:

```python
def test_run_scheduled_raises_when_lock_already_held(tmp_path, monkeypatch):
    lock_file_path = str(tmp_path / "scheduler.lock")
    holder_file = open(lock_file_path, "w")
    fcntl.flock(holder_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        was_called = {"called": False}
        monkeypatch.setattr(
            scheduler.run_once, "run_once", lambda: was_called.update(called=True)
        )

        with pytest.raises(scheduler.SchedulerLockedError):
            scheduler.run_scheduled(lock_file_path)

        assert was_called["called"] is False
    finally:
        holder_file.close()
```

- [ ] **Step 7: 執行測試確認這個新測試直接通過 (Step 4 的實作已涵蓋此邏輯), 且前一個測試仍通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_scheduler.py -v`
Expected: PASS (2 passed)

- [ ] **Step 8: Commit**

```bash
git add 04_paper_trading/scheduler.py tests/test_paper_trading_scheduler.py
git commit -m "feat: add scheduler lock via run_scheduled() to prevent overlapping runs"
```

---

### Task 2: `main()` 告警分流 (正常完成 / 鎖搶不到 / 其他例外)

**Files:**
- Modify: `04_paper_trading/scheduler.py`
- Test: `tests/test_paper_trading_scheduler.py`

**Interfaces:**
- Consumes: `scheduler.run_scheduled(lock_file_path: str) -> dict` 與 `scheduler.SchedulerLockedError` (Task 1 產出), `telegram_alerts.send_alert(message: str) -> None` (既有函式, `04_paper_trading/telegram_alerts.py:19`).
- Produces: `scheduler.main() -> None` (以 `sys.exit(code)` 結束, 供 `if __name__ == "__main__":` 呼叫, 也是 crontab 進入點).

- [ ] **Step 1: 寫失敗測試 : `main()` 正常完成時不呼叫 `telegram_alerts.send_alert`, exit code 為 0**

Append to `tests/test_paper_trading_scheduler.py`:

```python
def test_main_exits_zero_without_alert_when_successful(monkeypatch):
    monkeypatch.setattr(
        scheduler, "run_scheduled", lambda lock_file_path: {"symbols": {"BTCUSDT": {}}}
    )
    alerts = []
    monkeypatch.setattr(scheduler.telegram_alerts, "send_alert", lambda message: alerts.append(message))

    with pytest.raises(SystemExit) as exit_info:
        scheduler.main()

    assert exit_info.value.code == 0
    assert alerts == []
```

- [ ] **Step 2: 執行測試確認失敗 (此時 `main` 尚未定義)**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_scheduler.py -v`
Expected: FAIL : `AttributeError: module 'scheduler' has no attribute 'main'`

- [ ] **Step 3: 實作 `main()` 的正常完成路徑, 讓 Step 1 測試通過**

Append to `04_paper_trading/scheduler.py`:

```python
def main() -> None:
    record = run_scheduled(SCHEDULER_LOCK_PATH)
    print(f"排程執行完成, 處理標的數: {len(record['symbols'])}")
    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_scheduler.py -v`
Expected: PASS

- [ ] **Step 5: 寫失敗測試 : `main()` 在 `SchedulerLockedError` 情況下呼叫 `telegram_alerts.send_alert` 且 exit code 為 0**

Append to `tests/test_paper_trading_scheduler.py`:

```python
def test_main_sends_alert_and_exits_zero_when_locked(monkeypatch):
    def _raise_locked(lock_file_path):
        raise scheduler.SchedulerLockedError("鎖仍被持有")

    monkeypatch.setattr(scheduler, "run_scheduled", _raise_locked)
    alerts = []
    monkeypatch.setattr(scheduler.telegram_alerts, "send_alert", lambda message: alerts.append(message))

    with pytest.raises(SystemExit) as exit_info:
        scheduler.main()

    assert exit_info.value.code == 0
    assert len(alerts) == 1
    assert "尚未結束" in alerts[0]
```

- [ ] **Step 6: 執行測試確認失敗 (目前任何例外都會直接往外拋, 沒有 `except` 分支)**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_scheduler.py -v`
Expected: FAIL : 測試中 `scheduler.SchedulerLockedError` 未被捕捉, 直接以未預期例外形式往外拋

- [ ] **Step 7: 寫失敗測試 : `main()` 在 `run_once()` 拋出例外時呼叫 `telegram_alerts.send_alert` 且訊息包含錯誤內容, exit code 為 1**

Append to `tests/test_paper_trading_scheduler.py`:

```python
def test_main_sends_alert_and_exits_one_when_run_once_raises(monkeypatch):
    def _raise_unexpected(lock_file_path):
        raise RuntimeError("模擬 API 無回應")

    monkeypatch.setattr(scheduler, "run_scheduled", _raise_unexpected)
    alerts = []
    monkeypatch.setattr(scheduler.telegram_alerts, "send_alert", lambda message: alerts.append(message))

    with pytest.raises(SystemExit) as exit_info:
        scheduler.main()

    assert exit_info.value.code == 1
    assert len(alerts) == 1
    assert "模擬 API 無回應" in alerts[0]
```

- [ ] **Step 8: 實作 `main()` 完整的三分流邏輯, 讓 Step 5 與 Step 7 的測試通過**

Replace the `main()` written in Step 3 with:

```python
def main() -> None:
    try:
        record = run_scheduled(SCHEDULER_LOCK_PATH)
    except SchedulerLockedError as locked_error:
        telegram_alerts.send_alert("排程跳過: 上一次執行尚未結束")
        print(str(locked_error), file=sys.stderr)
        sys.exit(0)
    except Exception as error:
        telegram_alerts.send_alert(f"排程執行失敗: {error}")
        traceback.print_exc()
        sys.exit(1)
    print(f"排程執行完成, 處理標的數: {len(record['symbols'])}")
    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 9: 執行全部測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_scheduler.py -v`
Expected: PASS (5 passed)

- [ ] **Step 10: 執行整個專案測試套件, 確認沒有破壞既有測試**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/ -v`
Expected: PASS (全部通過, 含既有的 `test_paper_trading_run_once.py`、`test_telegram_alerts.py` 等)

- [ ] **Step 11: Commit**

```bash
git add 04_paper_trading/scheduler.py tests/test_paper_trading_scheduler.py
git commit -m "feat: add main() alert dispatch for scheduler success/locked/failure paths"
```

---

### Task 3: 手動驗證與部署 (crontab)

**Files:**
- None created or modified : 這個 task 是操作性驗證與系統 crontab 設定, 不改動專案檔案.

**Interfaces:**
- Consumes: `04_paper_trading/scheduler.py` 的 `if __name__ == "__main__": main()` 進入點 (Task 2 產出).
- Produces: 系統 crontab 內新增一行排程項目 (不是專案內產物).

- [ ] **Step 1: 確認 Task 1、Task 2 的自動化測試全數通過 (前置條件)**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_scheduler.py -v`
Expected: PASS (5 passed)

- [ ] **Step 2: 手動執行一次驗證成功路徑 (會真的呼叫 Binance Testnet 帳戶與 Telegram, 與 Slice 2 手動驗證同性質)**

Run: `cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && python3 scheduler.py; echo "exit code: $?"`
Expected: 印出 `排程執行完成, 處理標的數: N`, `exit code: 0`; 且 `04_paper_trading/logs/run_log.jsonl` 多了一筆新紀錄, `04_paper_trading/logs/scheduler.lock` 存在

- [ ] **Step 3: 立即再手動執行第二次, 驗證鎖释放後可以正常再次取得鎖 (确认鎖不会残留)**

Run: `cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && python3 scheduler.py; echo "exit code: $?"`
Expected: 同 Step 2, 再次成功完成, `exit code: 0` (证明 process 结束后鎖確實釋放, 不需要手動清鎖檔)

- [ ] **Step 4: 檢查目前系統 crontab, 確認沒有既有的 scheduler.py 相關項目 (避免重複新增)**

Run: `crontab -l`
Expected: 目前無 crontab 或無 `04_paper_trading/scheduler.py` 相關項目 (先前確認過 `crontab -l` 回傳 "no crontab for ubuntu")

- [ ] **Step 5: 新增 crontab 項目, 6 個固定 UTC 時間點觸發**

Run:

```bash
(crontab -l 2>/dev/null; echo "0 0,4,8,12,16,20 * * * cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 scheduler.py >> logs/cron.log 2>&1") | crontab -
```

Expected: 指令無錯誤輸出

- [ ] **Step 6: 驗證 crontab 項目已正確寫入**

Run: `crontab -l`
Expected: 輸出包含 `0 0,4,8,12,16,20 * * * cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 scheduler.py >> logs/cron.log 2>&1`

- [ ] **Step 7: 更新 `project_manage/ROADMAP.md`, 把(調度與通知)段落的 `scheduler.py` 加密貨幣項目勾選為完成**

Modify `project_manage/ROADMAP.md:199` from:

```
- [ ] `scheduler.py`: 加密貨幣每 4 小時一次(00:00 / 04:00 / 08:00 / 12:00 / 16:00 / 20:00 UTC)
```

to:

```
- [x] `scheduler.py`: 加密貨幣每 4 小時一次(00:00 / 04:00 / 08:00 / 12:00 / 16:00 / 20:00 UTC)
```

- [ ] **Step 8: Commit**

```bash
git add project_manage/ROADMAP.md
git commit -m "docs: check off crypto scheduler task in ROADMAP after crontab deployment"
```

---

## Self-Review

**Spec coverage:**
- `run_scheduled(lock_file_path)` + `fcntl.flock` 非阻塞鎖 + `SchedulerLockedError` → Task 1
- `main()` 三分流 (成功 / 鎖搶不到 / 其他例外) + exit code (0/0/1) + Telegram 告警 → Task 2
- 鎖檔預設路徑常數 `SCHEDULER_LOCK_PATH`, 可覆寫 → Task 1 Step 1 (`run_scheduled` 接受任意 `lock_file_path` 參數, `main()` 用常數呼叫)
- 沿用 `sys.path.insert` 手法直接 `import run_once` → Task 1 Step 1
- 5 項測試 (鎖可取得、鎖已持有、locked 告警+exit 0、失敗告警+exit 1、成功不告警+exit 0) → Task 1 + Task 2, 全部用 `tmp_path` 與 mock, 不碰真正鎖檔或網路
- crontab 部署 (6 個 UTC 時間點, 先手動驗證再寫入) → Task 3

**Placeholder scan:** 無 "TBD" / "類似 Task N" / 未展開程式碼的步驟 : 每個 Step 都有完整程式碼或明確指令與預期輸出.

**Type consistency:** `run_scheduled(lock_file_path: str) -> dict` 與 `SchedulerLockedError` 在 Task 1 定義, Task 2 的 `main()` 呼叫時的函式名稱、參數、回傳型別一致; `scheduler.run_once` 與 `scheduler.telegram_alerts` 在測試中皆以 `monkeypatch.setattr` 對模組屬性替換, 與既有 `test_paper_trading_run_once.py` 的 mock 慣例一致.
