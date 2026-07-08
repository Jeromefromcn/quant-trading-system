# Paper Trading Run-Summary Telegram Notification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After every successful scheduled paper-trading run, send one Telegram message summarizing whether a trade happened this run and what each symbol's outcome was, with a code-level toggle to disable it.

**Architecture:** All changes live in `04_paper_trading/scheduler.py`. A new pure function `_format_run_summary(record: dict) -> str` turns the `record` dict already returned by `run_once.run_once()` into a human-readable multi-line string. `main()` calls it and passes the result to the existing `telegram_alerts.send_alert(...)` only on the normal-completion path, gated by a new module-level constant `NOTIFY_RUN_SUMMARY`.

**Tech Stack:** Python 3.12, pytest, `monkeypatch` for mocking (existing project conventions, see `tests/test_paper_trading_scheduler.py`).

## Global Constraints

- No abbreviations in variable/function names: full descriptive names (per repo `CLAUDE.md`).
- Comments only for non-obvious *why*; every abbreviation in a comment needs its full form on first use.
- Reply/commit-message language: Traditional Chinese docstrings/comments follow existing file conventions (this file is entirely Traditional Chinese in prose, English identifiers).
- No `for`/`if-else` vectorization rule does NOT apply here: that rule is scoped to signal/indicator logic in `03_research/`, not this orchestration code.
- `fetch_failures` / `stale_symbols` / `circuit_breaker_triggered` must NOT appear in the new summary message: those already have separate alert paths (see spec `docs/superpowers/specs/2026-07-08-phase3-paper-trading-run-summary-notification-design.md`).
- The new notification fires only from `scheduler.main()`'s normal-completion path: never from `run_once.py` directly, never on the lock-skip or exception paths.
- `telegram_alerts.send_alert` must remain the only send path (no new notification channel, no retry logic).

---

### Task 1: `_format_run_summary` pure formatting function

**Files:**
- Modify: `04_paper_trading/scheduler.py`
- Test: `tests/test_paper_trading_scheduler.py`

**Interfaces:**
- Consumes: nothing from other tasks; reads the `record` dict shape already produced by `run_once.run_once()` (documented in `04_paper_trading/run_once.py` and `04_paper_trading/events.py`): `record["run_started_at"]` (str), `record["symbols"]` (dict of `symbol -> {"risk_decision": {...}, "execution_result": {...} | None}`), where `risk_decision["type"]` is one of `"NoActionNeeded"`, `"OrderEvent"`, `"RejectionEvent"`, and when non-null `execution_result["type"]` is one of `"FillEvent"`, `"FailEvent"`.
- Produces: `_format_run_summary(record: dict) -> str`, used by Task 2's `main()` wiring.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_paper_trading_scheduler.py` (append after the existing imports, before the first test function; keep `import scheduler` as-is):

```python
def test_format_run_summary_reports_no_trade_when_all_no_action():
    record = {
        "run_started_at": "2026-07-08T09:05:53+00:00",
        "symbols": {
            "BTCUSDT": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None},
            "ETHUSDT": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None},
        },
    }

    summary = scheduler._format_run_summary(record)

    assert "本次無成交" in summary
    assert "BTCUSDT: 本次無動作" in summary
    assert "ETHUSDT: 本次無動作" in summary


def test_format_run_summary_reports_trade_when_fill_event_present():
    record = {
        "run_started_at": "2026-07-08T09:05:53+00:00",
        "symbols": {
            "BTCUSDT": {
                "risk_decision": {
                    "type": "OrderEvent", "symbol": "BTCUSDT", "side": "BUY", "quantity": 0.015,
                },
                "execution_result": {
                    "type": "FillEvent", "symbol": "BTCUSDT", "side": "BUY", "quantity": 0.015,
                    "average_price": 68125.3, "order_id": "3021984710",
                    "commission": 0.0000045, "commission_asset": "BTC",
                },
            },
            "ETHUSDT": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None},
        },
    }

    summary = scheduler._format_run_summary(record)

    assert "本次有成交" in summary
    assert "BTCUSDT: 買入 0.015 @ 68125.3 成交 (order_id=3021984710)" in summary
    assert "ETHUSDT: 本次無動作" in summary


def test_format_run_summary_reports_rejection_reason_and_values():
    record = {
        "run_started_at": "2026-07-08T09:05:53+00:00",
        "symbols": {
            "ETHUSDT": {
                "risk_decision": {
                    "type": "RejectionEvent", "symbol": "ETHUSDT",
                    "reason": "correlation_exceeds_limit",
                    "computed_value": 0.87, "limit_value": 0.8,
                },
                "execution_result": None,
            },
        },
    }

    summary = scheduler._format_run_summary(record)

    assert "本次無成交" in summary
    assert "ETHUSDT: 交易被風控擋下 (correlation_exceeds_limit, 實際值=0.87, 上限=0.8)" in summary


def test_format_run_summary_reports_execution_failure_reason():
    record = {
        "run_started_at": "2026-07-08T09:05:53+00:00",
        "symbols": {
            "BTCUSDT": {
                "risk_decision": {
                    "type": "OrderEvent", "symbol": "BTCUSDT", "side": "SELL", "quantity": 0.01,
                },
                "execution_result": {
                    "type": "FailEvent", "symbol": "BTCUSDT",
                    "reason": "insufficient_balance", "raw_exchange_response": "{}",
                },
            },
        },
    }

    summary = scheduler._format_run_summary(record)

    assert "本次無成交" in summary
    assert "BTCUSDT: 下單失敗 (insufficient_balance)" in summary
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_paper_trading_scheduler.py -k format_run_summary -v`
Expected: 4 FAILED with `AttributeError: module 'scheduler' has no attribute '_format_run_summary'`

- [ ] **Step 3: Implement `_format_run_summary`**

In `04_paper_trading/scheduler.py`, insert the following two functions after the `SchedulerLockedError` class definition (after line 22's docstring, before the blank lines leading into `run_scheduled`):

```python
def _format_symbol_line(symbol: str, symbol_record: dict) -> str:
    """把單一標的的 risk_decision / execution_result 轉成摘要訊息裡的一行文字"""
    risk_decision = symbol_record["risk_decision"]
    decision_type = risk_decision["type"]
    if decision_type == "NoActionNeeded":
        return f"{symbol}: 本次無動作"
    if decision_type == "RejectionEvent":
        return (
            f"{symbol}: 交易被風控擋下 ({risk_decision['reason']}, "
            f"實際值={risk_decision['computed_value']}, 上限={risk_decision['limit_value']})"
        )
    execution_result = symbol_record["execution_result"]
    if execution_result["type"] == "FillEvent":
        side_label = "買入" if execution_result["side"] == "BUY" else "賣出"
        return (
            f"{symbol}: {side_label} {execution_result['quantity']} "
            f"@ {execution_result['average_price']} 成交 (order_id={execution_result['order_id']})"
        )
    return f"{symbol}: 下單失敗 ({execution_result['reason']})"


def _format_run_summary(record: dict) -> str:
    """
    把 run_once() 回傳的 record 轉成人類可讀的執行摘要, 供排程正常完成後發送 Telegram 通知
    (fetch_failures / stale_symbols / circuit_breaker_triggered 已有各自獨立的告警路徑,
    這裡不重複提及, 見設計文件 docs/superpowers/specs/2026-07-08-phase3-paper-trading-run-summary-notification-design.md)
    """
    symbol_records = record["symbols"]
    has_fill_event = any(
        symbol_record["execution_result"] is not None
        and symbol_record["execution_result"]["type"] == "FillEvent"
        for symbol_record in symbol_records.values()
    )
    header_line = f"Paper trading 執行摘要 ({record['run_started_at']})"
    trade_summary_line = "本次有成交" if has_fill_event else "本次無成交"
    symbol_lines = [
        _format_symbol_line(symbol, symbol_record)
        for symbol, symbol_record in symbol_records.items()
    ]
    return "\n".join([header_line, trade_summary_line, ""] + symbol_lines)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_paper_trading_scheduler.py -k format_run_summary -v`
Expected: 4 PASSED

- [ ] **Step 5: Run the full scheduler test file to confirm no regressions**

Run: `python3 -m pytest tests/test_paper_trading_scheduler.py -v`
Expected: all 9 tests PASSED (5 pre-existing + 4 new)

- [ ] **Step 6: Commit**

```bash
git add 04_paper_trading/scheduler.py tests/test_paper_trading_scheduler.py
git commit -m "feat: add run-summary formatting for paper trading Telegram notification"
```

---

### Task 2: Wire the summary notification into `main()` with a toggle

**Files:**
- Modify: `04_paper_trading/scheduler.py:18` (new constant), `04_paper_trading/scheduler.py:43-55` (`main()`)
- Test: `tests/test_paper_trading_scheduler.py`

**Interfaces:**
- Consumes: `_format_run_summary(record: dict) -> str` from Task 1.
- Produces: `NOTIFY_RUN_SUMMARY` module-level `bool` constant (default `True`), used by anyone wanting to toggle the notification (e.g. tests via `monkeypatch.setattr(scheduler, "NOTIFY_RUN_SUMMARY", False)`).

- [ ] **Step 1: Write the failing tests**

In `tests/test_paper_trading_scheduler.py`, replace the existing `test_main_exits_zero_without_alert_when_successful` test with two new tests (delete the old one, it asserts a behavior we're intentionally changing):

```python
def test_main_sends_summary_alert_and_exits_zero_when_successful(monkeypatch):
    fake_record = {
        "run_started_at": "2026-07-08T09:05:53+00:00",
        "symbols": {
            "BTCUSDT": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None},
        },
    }
    monkeypatch.setattr(scheduler, "run_scheduled", lambda lock_file_path: fake_record)
    alerts = []
    monkeypatch.setattr(scheduler.telegram_alerts, "send_alert", lambda message: alerts.append(message))

    with pytest.raises(SystemExit) as exit_info:
        scheduler.main()

    assert exit_info.value.code == 0
    assert len(alerts) == 1
    assert alerts[0] == scheduler._format_run_summary(fake_record)


def test_main_does_not_send_summary_when_notify_disabled(monkeypatch):
    fake_record = {
        "run_started_at": "2026-07-08T09:05:53+00:00",
        "symbols": {
            "BTCUSDT": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None},
        },
    }
    monkeypatch.setattr(scheduler, "run_scheduled", lambda lock_file_path: fake_record)
    monkeypatch.setattr(scheduler, "NOTIFY_RUN_SUMMARY", False)
    alerts = []
    monkeypatch.setattr(scheduler.telegram_alerts, "send_alert", lambda message: alerts.append(message))

    with pytest.raises(SystemExit) as exit_info:
        scheduler.main()

    assert exit_info.value.code == 0
    assert alerts == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_paper_trading_scheduler.py -k "main_sends_summary or notify_disabled" -v`
Expected: `test_main_sends_summary_alert_and_exits_zero_when_successful` FAILS with `assert len(alerts) == 1` (actual 0, since `main()` doesn't send anything yet); `test_main_does_not_send_summary_when_notify_disabled` FAILS with `AttributeError: <module 'scheduler'> does not have the attribute 'NOTIFY_RUN_SUMMARY'`

- [ ] **Step 3: Add the toggle constant and wire it into `main()`**

In `04_paper_trading/scheduler.py`, change line 18 from:

```python
SCHEDULER_LOCK_PATH = os.path.join(_paper_trading_directory, "logs", "scheduler.lock")
```

to:

```python
SCHEDULER_LOCK_PATH = os.path.join(_paper_trading_directory, "logs", "scheduler.lock")
NOTIFY_RUN_SUMMARY = True  # 排程正常完成後是否發送 Telegram 執行摘要, 設為 False 可關閉此通知
```

Then change `main()` (currently lines 43-55) from:

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
```

to:

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
    if NOTIFY_RUN_SUMMARY:
        telegram_alerts.send_alert(_format_run_summary(record))
    print(f"排程執行完成, 處理標的數: {len(record['symbols'])}")
    sys.exit(0)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_paper_trading_scheduler.py -v`
Expected: all 10 tests PASSED (the 9 from Task 1 minus the deleted one, plus the 2 new ones = 10)

- [ ] **Step 5: Commit**

```bash
git add 04_paper_trading/scheduler.py tests/test_paper_trading_scheduler.py
git commit -m "feat: send Telegram run-summary notification after successful scheduled paper trading run"
```

---

## Post-Plan Verification

- [ ] Run the full test suite to confirm nothing else broke: `python3 -m pytest tests/ -v`
- [ ] Manually inspect the final `04_paper_trading/scheduler.py` to confirm `NOTIFY_RUN_SUMMARY` sits next to `SCHEDULER_LOCK_PATH` and is easy for the user to find and flip.
