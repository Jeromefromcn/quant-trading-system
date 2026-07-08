# Phase 3 紙上交易 (paper trading) 每日報告 (`monitor.py`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `04_paper_trading/monitor.py`, 讓獨立 crontab 於每天 UTC 00:00 觸發時, 讀取 `logs/run_log.jsonl` 中前一個 UTC 日曆天的所有執行紀錄, 彙總成一則每日報告並透過 Telegram 發送.

**Architecture:** `monitor.py` 提供三個函式 : `_load_records_for_date(log_file_path, target_date)` 逐行讀 jsonl 並依 `run_started_at` 的 UTC 日期過濾; `_format_daily_report(records, target_date)` 是純函式, 把過濾後的 records 組成人類可讀的報告文字(成交交易、執行/拒絕次數統計、帳戶淨值變化、持倉明細、系統健康); `main()` 算出目標日期(執行當下 UTC 日期減一天), 依序讀檔, 格式化, 呼叫 `telegram_alerts.send_alert()`. 沿用 `scheduler.py` 已確立的 `sys.path.insert` 手法與純函式 + mock 測試風格.

**Tech Stack:** Python 3 標準庫(`json`, `datetime`), `pytest` + `monkeypatch`(既有測試慣例), 既有 `telegram_alerts.send_alert`, 系統 `crontab`.

## Global Constraints

- 本次只新增 `monitor.py` 一個檔案, 不修改 `run_once.py` / `scheduler.py` / `telegram_alerts.py` 的既有邏輯.
- 只讀 `logs/run_log.jsonl`, 不寫入(每日報告是唯讀彙總, 不產生新的每日狀態檔).
- 不處理美股, 不做 log 檔案輪替(rotation), YAGNI.
- 當日彙總只列成交交易 + 統計數字, 不逐次列出無動作的執行明細.
- 當日無任何執行紀錄時仍發送報告, 明確標註: 當日無任何執行紀錄.
- `EXPECTED_RUNS_PER_DAY = 6`(對應目前 crontab 每 4 小時觸發一次), 以模組層級常數定義並附註來源.
- `telegram_alerts.send_alert` 本身保證不拋例外, `monitor.py` 不需要再包一層防護.
- 成交交易段的時間以 `"%H:%M UTC"` 格式化(來自各 record 的 `run_started_at`).

---

## File Structure

- Create: `04_paper_trading/monitor.py` : 每日報告本體(讀檔 + 格式化 + 發送), 唯一新檔案.
- Create: `tests/test_paper_trading_monitor.py` : `monitor.py` 的單元測試, 全程 mock 或用 `tmp_path`, 不碰真正的 `logs/run_log.jsonl` 或外部網路.
- Modify: 系統 crontab(透過 `crontab` 指令, 非專案內檔案) : 部署 task 才會動到.
- Modify: `project_manage/ROADMAP.md:201` : 部署完成後把 `monitor.py` 項目勾選為完成.

---

### Task 1: `_load_records_for_date`

**Files:**
- Create: `04_paper_trading/monitor.py`
- Test: `tests/test_paper_trading_monitor.py`

**Interfaces:**
- Consumes: 無(本 task 是本檔案第一個函式, 不依賴其他 task 的產出).
- Produces: `monitor._load_records_for_date(log_file_path: str, target_date: date) -> list[dict]`, 依 `run_log.jsonl` 寫入順序回傳; 供 Task 3 的 `main()` 呼叫. `tests/conftest.py` 已把 `04_paper_trading` 加入 `sys.path`, 測試可直接 `import monitor`.

- [ ] **Step 1: 建立 `04_paper_trading/monitor.py` 骨架(模組 docstring、imports、常數), 先不寫函式邏輯**

```python
"""
Phase 3 紙上交易 (paper trading) 每日報告 (monitor) : 讀取 run_log.jsonl 中前一個 UTC 日曆天的
所有執行紀錄, 彙總成一則每日報告(成交交易, 執行/拒絕次數統計, 帳戶淨值變化, 持倉明細, 系統健康) ,
透過 Telegram 發送. 由獨立 crontab 於每天 UTC 00:00 觸發, 與 scheduler.py 的排程互不影響.
見設計文件 docs/superpowers/specs/2026-07-08-phase3-paper-trading-monitor-daily-report-design.md
用法: python3 monitor.py
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)

import telegram_alerts  # noqa: E402

LOG_FILE_PATH = os.path.join(_paper_trading_directory, "logs", "run_log.jsonl")
EXPECTED_RUNS_PER_DAY = 6  # 目前 crontab 每 4 小時觸發一次加密貨幣排程, 一天 6 次; 排程頻率改變需同步修改
```

- [ ] **Step 2: 寫失敗測試 : 只回傳指定 UTC 日期的紀錄, 跨日邊界正確分開**

Create `tests/test_paper_trading_monitor.py`:

```python
"""monitor.py 的每日報告測試 : 讀檔/日期過濾用 tmp_path, 格式化與發送用手造資料或 mock"""
import json
from datetime import date

import pytest

import monitor


def test_load_records_for_date_filters_by_utc_date_boundary(tmp_path):
    log_file_path = str(tmp_path / "run_log.jsonl")
    record_before_boundary = {"run_started_at": "2026-07-07T23:59:59+00:00", "marker": "yesterday"}
    record_after_boundary = {"run_started_at": "2026-07-08T00:00:01+00:00", "marker": "today"}
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record_before_boundary) + "\n")
        log_file.write(json.dumps(record_after_boundary) + "\n")

    records = monitor._load_records_for_date(log_file_path, date(2026, 7, 8))

    assert len(records) == 1
    assert records[0]["marker"] == "today"
```

- [ ] **Step 3: 執行測試確認失敗(此時 `_load_records_for_date` 尚未定義)**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: FAIL : `AttributeError: module 'monitor' has no attribute '_load_records_for_date'`

- [ ] **Step 4: 實作 `_load_records_for_date`, 讓 Step 2 測試通過**

Append to `04_paper_trading/monitor.py`:

```python
def _load_records_for_date(log_file_path: str, target_date: date) -> list[dict]:
    """
    逐行讀 log_file_path(jsonl, 每行一筆 run_once() 的執行紀錄) , 只保留 run_started_at
    (UTC 時區, ISO 格式) 落在 target_date 這個 UTC 日曆天的紀錄. 檔案不存在時回傳空列表
    (每日報告不該因為排程還沒跑過而失敗) ; 個別行解析失敗時略過該行並印出警告, 不中止整份報告
    """
    if not os.path.exists(log_file_path):
        return []
    matched_records = []
    with open(log_file_path, "r", encoding="utf-8") as log_file:
        for line_number, line in enumerate(log_file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                run_started_at = datetime.fromisoformat(record["run_started_at"])
            except (json.JSONDecodeError, KeyError, ValueError) as parse_error:
                print(f"略過無法解析的第 {line_number} 行: {parse_error}", file=sys.stderr)
                continue
            if run_started_at.astimezone(timezone.utc).date() == target_date:
                matched_records.append(record)
    return matched_records
```

- [ ] **Step 5: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: PASS

- [ ] **Step 6: 寫失敗測試 : 檔案不存在時回傳空列表, 不拋例外**

Append to `tests/test_paper_trading_monitor.py`:

```python
def test_load_records_for_date_returns_empty_list_when_file_missing(tmp_path):
    missing_log_file_path = str(tmp_path / "does_not_exist.jsonl")

    records = monitor._load_records_for_date(missing_log_file_path, date(2026, 7, 8))

    assert records == []
```

- [ ] **Step 7: 執行測試確認這個新測試直接通過(Step 4 的實作已涵蓋此邏輯), 且前一個測試仍通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: PASS(2 passed)

- [ ] **Step 8: Commit**

```bash
git add 04_paper_trading/monitor.py tests/test_paper_trading_monitor.py
git commit -m "feat: add _load_records_for_date to filter run_log.jsonl by UTC date"
```

---

### Task 2: `_format_daily_report`

**Files:**
- Modify: `04_paper_trading/monitor.py`
- Test: `tests/test_paper_trading_monitor.py`

**Interfaces:**
- Consumes: `record` 字典的既有欄位結構(見 `04_paper_trading/run_once.py` 的 `run_once()`) : 每個 record 頂層有 `run_started_at`(str, ISO), `account_equity_usdt`(float), `day_start_equity_usdt`(float), `stale_symbols`(dict, 可能為空), `circuit_breaker_triggered`(bool), `symbols`(dict, key 為標的代號); 每個 `symbols[symbol]` 有 `risk_decision`(dict, 含 `type` 為 `"NoActionNeeded"` / `"OrderEvent"` / `"RejectionEvent"` 之一)、`execution_result`(僅 `risk_decision.type == "OrderEvent"` 時非 `None`, 含 `type` 為 `"FillEvent"` / `"FailEvent"` 之一)、`current_base_asset_balance`(float, 僅在該標的有 `signal` 時存在)、`signal`(dict, 含 `latest_close_price`).
- Produces: `monitor._format_daily_report(records: list[dict], target_date: date) -> str`, 供 Task 3 的 `main()` 呼叫.

- [ ] **Step 1: 寫失敗測試 : 當日無任何執行紀錄時, 只輸出標題與提示, 不含其他段落**

Append to `tests/test_paper_trading_monitor.py`:

```python
def test_format_daily_report_reports_no_records_when_empty():
    report = monitor._format_daily_report([], date(2026, 7, 8))

    assert "每日報告 (2026-07-08 UTC)" in report
    assert "當日無任何執行紀錄" in report
    assert "今日無成交" not in report
```

- [ ] **Step 2: 執行測試確認失敗(此時 `_format_daily_report` 尚未定義)**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: FAIL : `AttributeError: module 'monitor' has no attribute '_format_daily_report'`

- [ ] **Step 3: 實作 `_format_daily_report` 的空日分支, 讓 Step 1 測試通過**

Append to `04_paper_trading/monitor.py`:

```python
def _format_daily_report(records: list[dict], target_date: date) -> str:
    """
    把 _load_records_for_date 過濾出的當日 records 組成人類可讀的每日報告文字.
    當日無任何紀錄時只回傳標題 + 提示, 其餘段落略過(仍要發送, 讓使用者能分辨
    今天真的沒交易, 與排程或 monitor.py 本身沒跑這兩種情況)
    """
    header_line = f"每日報告 ({target_date.isoformat()} UTC)"
    if not records:
        return f"{header_line}\n當日無任何執行紀錄"
    return header_line
```

- [ ] **Step 4: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: PASS

- [ ] **Step 5: 寫失敗測試 : 成交交易段列出方向/數量/價格/時間, 全天無成交時輸出: 今日無成交**

Append to `tests/test_paper_trading_monitor.py`:

```python
def test_format_daily_report_lists_fill_events():
    records = [
        {
            "run_started_at": "2026-07-08T12:00:01+00:00",
            "account_equity_usdt": 10000.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {
                "BTCUSDT": {
                    "risk_decision": {"type": "OrderEvent"},
                    "execution_result": {
                        "type": "FillEvent", "symbol": "BTCUSDT", "side": "BUY",
                        "quantity": 0.015, "average_price": 68125.3, "order_id": "1",
                    },
                    "current_base_asset_balance": 0.015,
                    "signal": {"latest_close_price": 68125.3},
                },
                "ETHUSDT": {
                    "risk_decision": {"type": "NoActionNeeded"},
                    "execution_result": None,
                    "current_base_asset_balance": 0.0,
                    "signal": {"latest_close_price": 3500.0},
                },
            },
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "12:00 UTC BTCUSDT: 買入 0.015 @ 68125.3" in report
    assert "今日無成交" not in report


def test_format_daily_report_reports_no_fills_when_all_no_action():
    records = [
        {
            "run_started_at": "2026-07-08T12:00:01+00:00",
            "account_equity_usdt": 10000.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {
                "BTCUSDT": {
                    "risk_decision": {"type": "NoActionNeeded"},
                    "execution_result": None,
                    "current_base_asset_balance": 0.0,
                    "signal": {"latest_close_price": 68125.3},
                },
            },
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "今日無成交" in report
```

- [ ] **Step 6: 執行測試確認失敗(目前 `_format_daily_report` 有紀錄時只回傳標題行)**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: FAIL : 兩個新測試皆失敗, 斷言的文字不存在於回傳字串中

- [ ] **Step 7: 實作成交交易段, 讓 Step 5 的兩個測試通過**

Replace the body of `_format_daily_report` in `04_paper_trading/monitor.py` (keep the empty-records branch unchanged, add after it):

```python
def _format_daily_report(records: list[dict], target_date: date) -> str:
    """
    把 _load_records_for_date 過濾出的當日 records 組成人類可讀的每日報告文字.
    當日無任何紀錄時只回傳標題 + 提示, 其餘段落略過(仍要發送, 讓使用者能分辨
    今天真的沒交易, 與排程或 monitor.py 本身沒跑這兩種情況)
    """
    header_line = f"每日報告 ({target_date.isoformat()} UTC)"
    if not records:
        return f"{header_line}\n當日無任何執行紀錄"

    fill_lines = []
    for record in records:
        run_time_label = datetime.fromisoformat(record["run_started_at"]).strftime("%H:%M UTC")
        for symbol, symbol_record in record["symbols"].items():
            execution_result = symbol_record["execution_result"]
            if execution_result is not None and execution_result["type"] == "FillEvent":
                side_label = "買入" if execution_result["side"] == "BUY" else "賣出"
                fill_lines.append(
                    f"{run_time_label} {symbol}: {side_label} {execution_result['quantity']} "
                    f"@ {execution_result['average_price']}"
                )
    fill_section = "\n".join(fill_lines) if fill_lines else "今日無成交"

    return "\n".join([header_line, "", fill_section])
```

- [ ] **Step 8: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: PASS(4 passed)

- [ ] **Step 9: 寫失敗測試 : 統計行含排程執行次數與風控拒絕次數**

Append to `tests/test_paper_trading_monitor.py`:

```python
def test_format_daily_report_counts_runs_and_rejections():
    records = [
        {
            "run_started_at": "2026-07-08T08:00:00+00:00",
            "account_equity_usdt": 10000.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {
                "BTCUSDT": {
                    "risk_decision": {
                        "type": "RejectionEvent", "reason": "max_loss_per_trade",
                        "computed_value": 0.02, "limit_value": 0.015,
                    },
                    "execution_result": None,
                    "current_base_asset_balance": 0.0,
                    "signal": {"latest_close_price": 68000.0},
                },
            },
        },
        {
            "run_started_at": "2026-07-08T12:00:00+00:00",
            "account_equity_usdt": 10000.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {
                "ETHUSDT": {
                    "risk_decision": {
                        "type": "RejectionEvent", "reason": "correlation_limit",
                        "computed_value": 0.9, "limit_value": 0.8,
                    },
                    "execution_result": None,
                    "current_base_asset_balance": 0.0,
                    "signal": {"latest_close_price": 3500.0},
                },
            },
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "今日排程執行 2 / 預期 6 次" in report
    assert "風控拒絕 2 次" in report
```

- [ ] **Step 10: 執行測試確認失敗(統計行尚未實作)**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: FAIL : 斷言的統計文字不存在於回傳字串中

- [ ] **Step 11: 實作統計行, 讓 Step 9 測試通過**

Modify the `return` statement of `_format_daily_report` in `04_paper_trading/monitor.py`:

```python
    rejection_count = sum(
        1
        for record in records
        for symbol_record in record["symbols"].values()
        if symbol_record["risk_decision"]["type"] == "RejectionEvent"
    )
    stats_line = f"今日排程執行 {len(records)} / 預期 {EXPECTED_RUNS_PER_DAY} 次, 風控拒絕 {rejection_count} 次"

    return "\n".join([header_line, "", fill_section, "", stats_line])
```

- [ ] **Step 12: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: PASS(5 passed)

- [ ] **Step 13: 寫失敗測試 : 帳戶淨值段顯示組點/結束淨值與漲跌 %(含下跌的負值情境)**

Append to `tests/test_paper_trading_monitor.py`:

```python
def test_format_daily_report_shows_equity_change_percentage():
    records = [
        {
            "run_started_at": "2026-07-08T00:00:00+00:00",
            "account_equity_usdt": 9800.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {},
        },
        {
            "run_started_at": "2026-07-08T20:00:00+00:00",
            "account_equity_usdt": 9700.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {},
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "帳戶淨值從 10000.00 變化至 9700.00 USDT (-3.00%)" in report
```

- [ ] **Step 14: 執行測試確認失敗(帳戶淨值段尚未實作)**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: FAIL : 斷言的帳戶淨值文字不存在於回傳字串中

- [ ] **Step 15: 實作帳戶淨值段, 讓 Step 13 測試通過**

Modify the `return` statement of `_format_daily_report` in `04_paper_trading/monitor.py`:

```python
    day_start_equity = records[0]["day_start_equity_usdt"]
    day_end_equity = records[-1]["account_equity_usdt"]
    equity_change_percentage = (day_end_equity - day_start_equity) / day_start_equity * 100
    equity_line = (
        f"帳戶淨值從 {day_start_equity:.2f} 變化至 {day_end_equity:.2f} USDT "
        f"({equity_change_percentage:+.2f}%)"
    )

    return "\n".join([header_line, "", fill_section, "", stats_line, equity_line])
```

- [ ] **Step 16: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: PASS(6 passed)

- [ ] **Step 17: 寫失敗測試 : 持倉明細正確列出非 0 餘額, 略過 0 餘額標的; 全部為 0 時輸出: 目前無持倉**

Append to `tests/test_paper_trading_monitor.py`:

```python
def test_format_daily_report_lists_nonzero_positions():
    records = [
        {
            "run_started_at": "2026-07-08T20:00:00+00:00",
            "account_equity_usdt": 10000.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {
                "BTCUSDT": {
                    "risk_decision": {"type": "NoActionNeeded"},
                    "execution_result": None,
                    "current_base_asset_balance": 0.015,
                    "signal": {"latest_close_price": 68000.0},
                },
                "ETHUSDT": {
                    "risk_decision": {"type": "NoActionNeeded"},
                    "execution_result": None,
                    "current_base_asset_balance": 0.0,
                    "signal": {"latest_close_price": 3500.0},
                },
            },
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "BTCUSDT: 0.015 (約 1020.00 USDT)" in report
    assert "ETHUSDT:" not in report


def test_format_daily_report_shows_no_positions_when_all_zero():
    records = [
        {
            "run_started_at": "2026-07-08T20:00:00+00:00",
            "account_equity_usdt": 10000.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {
                "BTCUSDT": {
                    "risk_decision": {"type": "NoActionNeeded"},
                    "execution_result": None,
                    "current_base_asset_balance": 0.0,
                    "signal": {"latest_close_price": 68000.0},
                },
            },
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "目前無持倉" in report


def test_format_daily_report_skips_stale_symbol_missing_signal_and_balance():
    records = [
        {
            "run_started_at": "2026-07-08T20:00:00+00:00",
            "account_equity_usdt": 10000.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {"BTCUSDT": {"time_since_close_seconds": 999, "threshold_seconds": 129600}},
            "circuit_breaker_triggered": False,
            "symbols": {
                "BTCUSDT": {
                    "risk_decision": {
                        "type": "RejectionEvent", "reason": "data_staleness",
                        "computed_value": None, "limit_value": None,
                    },
                    "execution_result": None,
                },
                "ETHUSDT": {
                    "risk_decision": {"type": "NoActionNeeded"},
                    "execution_result": None,
                    "current_base_asset_balance": 0.02,
                    "signal": {"latest_close_price": 3500.0},
                },
            },
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "ETHUSDT: 0.02 (約 70.00 USDT)" in report
```

`BTCUSDT` above is a stale symbol : `run_once.py` only writes the `signal` and `current_base_asset_balance` keys for a symbol when it is present in `signal_events`(see `run_once.py:150-159`), and a stale symbol never reaches that point(see `run_once.py:100`, the staleness check `continue`s before `signal_agent.decide` is called). So `symbol_record` for a stale symbol only ever has `risk_decision` and `execution_result` : the position section must not assume every symbol in `records[-1]["symbols"]` has `current_base_asset_balance` or `signal`.

- [ ] **Step 18: 執行測試確認失敗(持倉明細段尚未實作)**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: FAIL : 斷言的持倉文字不存在於回傳字串中

- [ ] **Step 19: 實作持倉明細段, 讓 Step 17 測試通過(含 Step 17 新增的 stale-symbol 測試, 見上方說明: `current_base_asset_balance` 不保證存在, 需先檢查 key 是否存在再讀取)**

Modify the `return` statement of `_format_daily_report` in `04_paper_trading/monitor.py`:

```python
    latest_symbols = records[-1]["symbols"]
    position_lines = []
    for symbol, symbol_record in latest_symbols.items():
        if "current_base_asset_balance" not in symbol_record:
            continue
        balance = symbol_record["current_base_asset_balance"]
        if balance != 0:
            latest_close_price = symbol_record["signal"]["latest_close_price"]
            position_lines.append(f"{symbol}: {balance} (約 {balance * latest_close_price:.2f} USDT)")
    position_section = "\n".join(position_lines) if position_lines else "目前無持倉"

    return "\n".join(
        [header_line, "", fill_section, "", stats_line, equity_line, "", "持倉:", position_section]
    )
```

- [ ] **Step 20: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: PASS(9 passed)

- [ ] **Step 21: 寫失敗測試 : 系統健康段統計數據異常與熔斷觸發次數**

Append to `tests/test_paper_trading_monitor.py`:

```python
def test_format_daily_report_counts_staleness_and_circuit_breaker_triggers():
    records = [
        {
            "run_started_at": "2026-07-08T08:00:00+00:00",
            "account_equity_usdt": 9600.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {"BTCUSDT": {"time_since_close_seconds": 999, "threshold_seconds": 129600}},
            "circuit_breaker_triggered": True,
            "symbols": {},
        },
        {
            "run_started_at": "2026-07-08T12:00:00+00:00",
            "account_equity_usdt": 9600.0,
            "day_start_equity_usdt": 10000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {},
        },
    ]

    report = monitor._format_daily_report(records, date(2026, 7, 8))

    assert "數據異常保護觸發 1 次" in report
    assert "每日熔斷觸發 1 次" in report
```

- [ ] **Step 22: 執行測試確認失敗(系統健康段尚未實作)**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: FAIL : 斷言的系統健康文字不存在於回傳字串中

- [ ] **Step 23: 實作系統健康段, 讓 Step 21 測試通過**

Modify the `return` statement of `_format_daily_report` in `04_paper_trading/monitor.py`:

```python
    staleness_trigger_count = sum(1 for record in records if record["stale_symbols"])
    circuit_breaker_trigger_count = sum(1 for record in records if record["circuit_breaker_triggered"])
    health_line = (
        f"系統健康: 數據異常保護觸發 {staleness_trigger_count} 次, "
        f"每日熔斷觸發 {circuit_breaker_trigger_count} 次"
    )

    return "\n".join(
        [
            header_line, "", fill_section, "", stats_line, equity_line,
            "", "持倉:", position_section, "", health_line,
        ]
    )
```

- [ ] **Step 24: 執行全部測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: PASS(11 passed)

- [ ] **Step 25: Commit**

```bash
git add 04_paper_trading/monitor.py tests/test_paper_trading_monitor.py
git commit -m "feat: add _format_daily_report to summarize daily paper trading activity"
```

---

### Task 3: `main()` 串接讀檔, 格式化, 發送

**Files:**
- Modify: `04_paper_trading/monitor.py`
- Test: `tests/test_paper_trading_monitor.py`

**Interfaces:**
- Consumes: `monitor._load_records_for_date(log_file_path: str, target_date: date) -> list[dict]`(Task 1)、`monitor._format_daily_report(records: list[dict], target_date: date) -> str`(Task 2)、`telegram_alerts.send_alert(message: str) -> None`(既有函式, `04_paper_trading/telegram_alerts.py:19`).
- Produces: `monitor.main() -> None`, 供 `if __name__ == "__main__":` 呼叫, 也是 crontab 進入點.

- [ ] **Step 1: 寫失敗測試 : `main()` 以執行當下 UTC 日期減一天為目標日期, 依序呼叫讀檔, 格式化, 發送**

Change the top of `tests/test_paper_trading_monitor.py` from:

```python
"""monitor.py 的每日報告測試 : 讀檔/日期過濾用 tmp_path, 格式化與發送用手造資料或 mock"""
from datetime import date
```

to:

```python
"""monitor.py 的每日報告測試 : 讀檔/日期過濾用 tmp_path, 格式化與發送用手造資料或 mock"""
from datetime import date, datetime, timedelta, timezone
```

Append to `tests/test_paper_trading_monitor.py`:

```python
def test_main_loads_formats_and_sends_report_for_previous_utc_day(monkeypatch):
    captured = {}

    def _fake_load_records_for_date(log_file_path, target_date):
        captured["log_file_path"] = log_file_path
        captured["target_date"] = target_date
        return [{"marker": "fake_record"}]

    def _fake_format_daily_report(records, target_date):
        captured["records"] = records
        captured["format_target_date"] = target_date
        return "格式化後的報告文字"

    sent_messages = []
    monkeypatch.setattr(monitor, "_load_records_for_date", _fake_load_records_for_date)
    monkeypatch.setattr(monitor, "_format_daily_report", _fake_format_daily_report)
    monkeypatch.setattr(monitor.telegram_alerts, "send_alert", lambda message: sent_messages.append(message))

    monitor.main()

    expected_target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    assert captured["target_date"] == expected_target_date
    assert captured["format_target_date"] == expected_target_date
    assert captured["records"] == [{"marker": "fake_record"}]
    assert sent_messages == ["格式化後的報告文字"]
```

- [ ] **Step 2: 執行測試確認失敗(此時 `main` 尚未定義)**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: FAIL : `AttributeError: module 'monitor' has no attribute 'main'`

- [ ] **Step 3: 實作 `main()`, 讓 Step 1 測試通過**

Append to `04_paper_trading/monitor.py`:

```python
def main() -> None:
    target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    records = _load_records_for_date(LOG_FILE_PATH, target_date)
    report = _format_daily_report(records, target_date)
    telegram_alerts.send_alert(report)
    print(f"每日報告已發送 ({target_date.isoformat()} UTC), 涵蓋 {len(records)} 筆執行紀錄")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: PASS(11 passed)

- [ ] **Step 5: 執行整個專案測試套件, 確認沒有破壞既有測試**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/ -v`
Expected: PASS(全部通過, 含既有的 `test_paper_trading_scheduler.py`、`test_paper_trading_run_once.py` 等)

- [ ] **Step 6: Commit**

```bash
git add 04_paper_trading/monitor.py tests/test_paper_trading_monitor.py
git commit -m "feat: add main() to send daily paper trading report via Telegram"
```

---

### Task 4: 手動驗證與部署(crontab)

**Files:**
- Modify: `project_manage/ROADMAP.md:201`

**Interfaces:**
- Consumes: `04_paper_trading/monitor.py` 的 `if __name__ == "__main__": main()` 進入點(Task 3 產出).
- Produces: 系統 crontab 內新增一行獨立排程項目(不是專案內產物).

- [ ] **Step 1: 確認 Task 1-3 的自動化測試全數通過(前置條件)**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_monitor.py -v`
Expected: PASS(11 passed)

- [ ] **Step 2: 手動執行一次驗證(會真的呼叫 Telegram; 若當日 `run_log.jsonl` 尚無前一 UTC 日曆天的紀錄, 預期送出內容為當日無任何執行紀錄, 屬正常情況)**

Run: `cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && python3 monitor.py; echo "exit code: $?"`
Expected: 印出 `每日報告已發送 (YYYY-MM-DD UTC), 涵蓋 N 筆執行紀錄`, `exit code: 0`; 且 Telegram 收到對應內容的訊息

- [ ] **Step 3: 檢查目前系統 crontab, 確認沒有既有的 `monitor.py` 相關項目(避免重複新增)**

Run: `crontab -l`
Expected: 輸出包含既有的 `scheduler.py` 排程項目, 但不含 `monitor.py`

- [ ] **Step 4: 新增 crontab 項目, 每天 UTC 00:00 觸發**

Run:

```bash
(crontab -l 2>/dev/null; echo "0 0 * * * cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 monitor.py >> logs/cron.log 2>&1") | crontab -
```

Expected: 指令無錯誤輸出

- [ ] **Step 5: 驗證 crontab 項目已正確寫入, 且未覆蓋既有的 `scheduler.py` 項目**

Run: `crontab -l`
Expected: 輸出同時包含 `scheduler.py` 與 `0 0 * * * cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 monitor.py >> logs/cron.log 2>&1` 兩行

- [ ] **Step 6: 更新 `project_manage/ROADMAP.md`, 把 `monitor.py` 每日報告項目勾選為完成**

Modify `project_manage/ROADMAP.md:201` from:

```
- [ ] `monitor.py`: 每日自動生成報告並發送 Telegram(含信號, 執行結果, 持倉, 帳戶摘要, 系統健康)
```

to:

```
- [x] `monitor.py`: 每日自動生成報告並發送 Telegram(含信號, 執行結果, 持倉, 帳戶摘要, 系統健康)
```

- [ ] **Step 7: Commit**

```bash
git add project_manage/ROADMAP.md
git commit -m "docs: check off monitor.py daily report task in ROADMAP after crontab deployment"
```

---

## Self-Review

**Spec coverage:**
- `_load_records_for_date(log_file_path, target_date)` 讀檔 + UTC 日期過濾 + 檔案不存在回傳空列表 → Task 1
- `_format_daily_report(records, target_date)` 標題 + 空日分支 + 成交交易段 + 統計行 + 帳戶淨值段 + 持倉明細段 + 系統健康段 → Task 2(逐段落 TDD)
- `EXPECTED_RUNS_PER_DAY = 6` 常數與來源註解 → Task 1 Step 1
- `main()` 目標日期計算(執行當下 UTC 日期減一天) + 串接三步驟 → Task 3
- 個別行 JSON 解析失敗略過並印警告, 不中止整份報告 → Task 1 Step 4
- 部署 : 獨立 crontab(不與 `scheduler.py` 衝突), 先手動驗證再寫入, 完成後勾選 ROADMAP → Task 4

**Placeholder scan:** 無 "TBD" / "類似 Task N" / 未展開程式碼的步驟 : 每個 Step 都有完整程式碼或明確指令與預期輸出.

**Type consistency:** `_load_records_for_date(log_file_path: str, target_date: date) -> list[dict]` 在 Task 1 定義, Task 3 的 `main()` 呼叫時參數順序與型別一致; `_format_daily_report(records: list[dict], target_date: date) -> str` 在 Task 2 定義, Task 3 呼叫時一致; `LOG_FILE_PATH`、`EXPECTED_RUNS_PER_DAY` 在 Task 1 Step 1 定義後, 後續 task 直接引用, 未重新定義; 測試中 `monitor.telegram_alerts` 以 `monkeypatch.setattr` 對模組屬性替換, 與 `test_paper_trading_scheduler.py` 的 mock 慣例一致.
