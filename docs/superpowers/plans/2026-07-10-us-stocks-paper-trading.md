# US Stocks Paper Trading (Alpaca) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second, independent Phase 3 paper-trading pipeline for VOO + QQQ against Alpaca Paper Trading, reusing the frozen `exp_002` strategy and the existing crypto pipeline's shared agents, executing once per US trading day via limit-on-open / market-on-open orders.

**Architecture:** Mirrors the existing `04_paper_trading` crypto pipeline (`data → signal → risk → execution`, one `run_once`, one `scheduler`, one `monitor`) file-for-file, but with an Alpaca-specific client and agents, its own log/state files, and a single daily run (no polling) since orders are queued with the exchange for the next opening auction instead of executed immediately.

**Tech Stack:** Python 3.11+, pandas, requests, python-dotenv, pytest + monkeypatch (no HTTP mocking library — this codebase's convention is to unit-test pure functions only and manually verify networked functions against the real sandbox).

## Global Constraints

- No `for` loops or `if-else` in signal/indicator logic — vectorize (project CLAUDE.md). Not applicable to this plan's orchestration/IO code, which is control flow, not signal logic — same exemption already used by `execution_agent.py`'s polling loop.
- No abbreviations in variable/column names — full descriptive names (project CLAUDE.md).
- Every abbreviation in a comment needs its full form in parentheses on first use.
- Commit after every task; imperative commit messages, one logical change each.
- Full spec: `docs/superpowers/specs/2026-07-10-phase3-us-stocks-paper-trading-design.md` — read it before starting if anything below is ambiguous.
- Frozen strategy parameters (reused verbatim, do not touch): `03_research/04_experiments/exp_002_ema_adx/config.py` — `initial_capital=10_000.0, risk_per_trade_percentage=0.01, atr_stop_multiplier=2.0, atr_period=14, max_position_fraction=1.0`.
- `RISK_LIMITS` for the stocks pipeline are numerically identical to the crypto pipeline's: `max_loss_per_trade_fraction=0.015, max_daily_loss_fraction=0.04, max_positions_by_market={"crypto": 3, "stocks": 5}, max_correlation=0.8`.
- Test file convention in this repo: only **pure functions** get automated unit tests with mocked collaborators (via `monkeypatch.setattr` on the module attribute, never a generic HTTP-mocking library). Functions that make real network calls (`requests.get`/`.post` directly) are exercised manually against the real sandbox at the end of the plan, never mocked at the `requests` layer in `tests/`.
- `tests/conftest.py` already adds `04_paper_trading` and `04_paper_trading/agents` to `sys.path`, so all new files in this plan are importable in tests by bare module name (e.g. `import run_once_stocks`) with no additional conftest changes.

---

## Task 0: Repo-wide Chinese punctuation cleanup (prerequisite, precedes Task 1)

**Why this is here:** pre-flight review of this plan found that its own new-code samples used em-dash (`—`), corner-bracket quotes (`「」`), and arrows (`→`) in Chinese docstrings/comments, violating CLAUDE.md's rule ("English punctuation only (`.` `,` `!` `?` `:` `;` `()`), even in Chinese"). Those plan samples have already been fixed inline (Tasks 1-8 below are clean). Checking the actual repo turned up the same pattern pre-existing across the whole codebase: 165 occurrences in 62 files. The user asked for a full-repo cleanup before starting the VOO feature work, done as its own prerequisite pass. This is pure comment/docstring/print-message punctuation substitution — confirmed via repo-wide grep that no test asserts on any string containing these characters (no `match=` regex in `tests/*.py` references them, no exact-substring assertion does either), so there is no runtime-behavior risk, only a text-content risk.

**Hard constraint for `03_research/04_experiments/*/config.py` (9 files: `exp_001` through `exp_008`, plus `_template`):** these are frozen historical experiment records; `exp_002_ema_adx/config.py` specifically is imported live by `agents/signal_agent.py` for real trading decisions. Only comment/docstring text may change in these 9 files. The parameter dictionaries themselves (every `key: value` line, e.g. `"initial_capital": 10_000.0`) must remain byte-for-byte identical — no reformatting, no reordering, no whitespace changes inside the dict literals. Each reviewer for the sub-task touching these files must diff the parameter dict lines before/after and confirm zero changes.

**Replacement rules** (apply consistently, judgment call per instance which fits):
- Em-dash (`—`) used as a clause separator introducing elaboration → replace with `:`
- Em-dash used as a parenthetical aside (`X — Y — Z`) → replace with `,` or rephrase as a separate sentence ending in `.`
- Corner-bracket quotes (`「...」`) → remove the brackets, keep the enclosed text plain (matches the style already used in this plan's own fixed code, e.g. `alpaca_paper_trading_client.py`'s docstring)
- Arrow (`→`) used to show a pipeline/sequence (`A → B → C`) → rephrase in prose (e.g. "A, 接著 B, 最後 C" or "資料流程依序是 A, B, C") — do not introduce `->` or other ASCII arrows as a substitute, that is not in the whitelist either
- Never touch anything else: no rewording beyond what's needed to remove the disallowed character, no logic changes, no reordering of code

**Sub-tasks (dispatch and review each independently, same implementer/reviewer loop as Tasks 1-9):**

- **Task 0a:** `01_learning/` — 14 files: `01_pandas/{02_shift_rolling,03_boolean_indexing,04_groupby_merge_resample,05_apply,06_quant_examples}.py`, `02_concepts/{01_ohlcv_basics,03_atr,04_sharpe_drawdown,05_position_sizing,06_simple_backtest,07_backtest_metrics,08_overfitting,09_lookahead_bias,10_train_test_split}.py`. No test suite covers this directory (per CLAUDE.md's architecture table, "run and study, not imported") — verification is `python3 <file>` still runs without a `SyntaxError` for each touched file (these are standalone scripts; a full behavioral run is not required, just confirm the file still parses and imports cleanly).
- **Task 0b:** `02_data/` — 3 files: `fetchers/binance_fetcher.py`, `fetchers/alpaca_fetcher.py`, `validate_against_independent_source.py`. Verify with `pytest tests/test_binance_fetcher_parsing.py -v`.
- **Task 0c:** `03_research/` — 20 files: `03_backtest/{report,metrics,engine}.py`, `02_strategies/{trend_following,base}.py`, `01_indicators/{volatility,trend,momentum}.py`, `04_experiments/{new_experiment,run_experiment}.py`, `04_experiments/exp_002_ema_adx/factor_regression.py`, and the 9 frozen config files under the hard constraint above: `04_experiments/_template/config.py`, `04_experiments/exp_001_ema_baseline/config.py`, `04_experiments/exp_002_ema_adx/config.py`, `04_experiments/exp_003_ema_slow/config.py`, `04_experiments/exp_004_trailing_stop/config.py`, `04_experiments/exp_005_tight_trailing/config.py`, `04_experiments/exp_006_eth/config.py`, `04_experiments/exp_007_spy/config.py`, `04_experiments/exp_008_qqq/config.py`. Verify with `pytest tests/test_backtest.py tests/test_indicators.py tests/test_trailing_stop.py tests/test_engine_invariants.py tests/test_risk.py -v`.
- **Task 0d:** `04_paper_trading/` — 9 files: `events.py`, `daily_risk_state.py`, `binance_testnet_client.py`, `telegram_alerts.py`, `run_once.py`, `agents/signal_agent.py`, `agents/execution_agent.py`, `agents/risk_agent.py`, `agents/data_agent.py`. This is the live production crypto paper-trading pipeline (real cron jobs running against real Binance Testnet) — verify with the full existing paper-trading test subset: `pytest tests/test_paper_trading_*.py tests/test_daily_risk_state.py tests/test_telegram_alerts.py tests/test_binance_testnet_client_rounding.py -v`.
- **Task 0e:** `tests/` — 16 files: `test_telegram_alerts.py`, `test_paper_trading_data_agent.py`, `test_daily_risk_state.py`, `test_binance_testnet_client_rounding.py`, `test_paper_trading_run_once.py`, `test_engine_invariants.py`, `test_paper_trading_events.py`, `test_indicators.py`, `test_trailing_stop.py`, `test_paper_trading_signal_agent.py`, `test_paper_trading_risk_agent.py`, `test_backtest.py`, `test_paper_trading_execution_agent.py`, `conftest.py`, `test_binance_fetcher_parsing.py`, `test_risk.py`. These occurrences are all in docstrings/comments, not in string literals compared by assertions (confirmed during pre-flight, see above) — verify with the full suite: `pytest tests/ -v`.

**After all five sub-tasks are reviewed clean:** run `pytest tests/ -v` once more (full suite) and `grep -rlE "—|「|」|→" --include="*.py" .` from the repo root to confirm zero remaining matches before proceeding to Task 1.

---

## File Structure

```
04_paper_trading/
  events.py                          (Task 1 — modify: OrderEvent.limit_price, new SubmittedEvent)
  alpaca_paper_trading_client.py     (Task 3 — new)
  run_once_stocks.py                 (Task 6 — new)
  scheduler_stocks.py                (Task 7 — new)
  monitor_stocks.py                  (Task 8 — new)
  agents/
    stock_data_agent.py              (Task 4 — new)
    stock_execution_agent.py         (Task 5 — new)
    risk_agent.py                    (Task 2 — modify: SYMBOL_MARKET_TYPES, limit_price population)
  logs/                              (gitignore-excluded, created at runtime)
    run_log_stocks.jsonl
    daily_risk_state_stocks.json
    scheduler_stocks.lock
tests/
  test_paper_trading_events.py            (Task 1 — extend)
  test_paper_trading_risk_agent.py        (Task 2 — extend)
  test_alpaca_paper_trading_client_rounding.py  (Task 3 — new)
  test_stock_data_agent.py                (Task 4 — new)
  test_stock_execution_agent.py           (Task 5 — new)
  test_run_once_stocks.py                 (Task 6 — new)
  test_scheduler_stocks.py                (Task 7 — new)
  test_monitor_stocks.py                  (Task 8 — new)
docs/superpowers/specs/2026-07-10-phase3-us-stocks-paper-trading-design.md  (Task 9 — append verification log)
project_manage/ROADMAP.md              (Task 9 — check off completed items)
```

Task order follows the dependency chain: `events.py` → `risk_agent.py` → `alpaca_paper_trading_client.py` → `stock_data_agent.py` → `stock_execution_agent.py` → `run_once_stocks.py` → `scheduler_stocks.py` → `monitor_stocks.py` → wiring/verification.

---

### Task 1: `events.py` — add `OrderEvent.limit_price` and `SubmittedEvent`

**Files:**
- Modify: `04_paper_trading/events.py`
- Test: `tests/test_paper_trading_events.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `OrderEvent(symbol: str, side: str, quantity: float, limit_price: float | None = None)` (existing dataclass, one new optional field). `SubmittedEvent(symbol: str, side: str, quantity: float, order_id: str, limit_price: float | None = None)` (new dataclass) — every later task that imports `events` relies on these exact names and field names.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_paper_trading_events.py` (update the existing import line at the top of the file to add `SubmittedEvent`):

```python
from events import FailEvent, FillEvent, OrderEvent, RejectionEvent, SignalEvent, SubmittedEvent
```

Add these test functions at the end of the file:

```python
def test_order_event_defaults_limit_price_to_none():
    order_event = OrderEvent(symbol="BTCUSDT", side="BUY", quantity=0.01)
    assert order_event.limit_price is None


def test_order_event_holds_limit_price_when_provided():
    order_event = OrderEvent(symbol="VOO", side="BUY", quantity=10, limit_price=550.25)
    assert order_event.limit_price == 550.25


def test_submitted_event_holds_all_fields():
    submitted_event = SubmittedEvent(
        symbol="VOO", side="BUY", quantity=10.0, order_id="abc123", limit_price=550.25
    )
    assert submitted_event.symbol == "VOO"
    assert submitted_event.side == "BUY"
    assert submitted_event.quantity == 10.0
    assert submitted_event.order_id == "abc123"
    assert submitted_event.limit_price == 550.25


def test_submitted_event_defaults_limit_price_to_none():
    submitted_event = SubmittedEvent(symbol="VOO", side="SELL", quantity=10.0, order_id="abc123")
    assert submitted_event.limit_price is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_paper_trading_events.py -v`
Expected: FAIL — `ImportError: cannot import name 'SubmittedEvent' from 'events'`

- [ ] **Step 3: Implement**

In `04_paper_trading/events.py`, modify the existing `OrderEvent` class:

```python
@dataclass
class OrderEvent:
    """risk_agent 核准後的下單指令"""

    symbol: str
    side: str  # "BUY" 或 "SELL"
    quantity: float
    limit_price: float | None = None  # 僅美股開盤限價單(limit-on-open, LOO) 使用; 加密貨幣市價單維持 None
```

Add a new dataclass after `FailEvent` (end of file):

```python
@dataclass
class SubmittedEvent:
    """
    execution_agent 確認委託已被交易所接受, 但尚未確認成交: 美股開盤限價/市價委託單
    (limit-on-open / market-on-open) 在收盤後送出時市場尚未開盤, 要等次日開盤拍賣才會撮合,
    與加密貨幣市價單送出即成交的 FillEvent 語意不同, 故用獨立型別區分已送出與已確認成交
    """

    symbol: str
    side: str
    quantity: float
    order_id: str
    limit_price: float | None = None  # 市價委託 (market-on-open, MOO) 無限價, 維持 None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_paper_trading_events.py -v`
Expected: PASS, all tests green.

- [ ] **Step 5: Run full test suite to confirm no regression**

Run: `pytest tests/ -v`
Expected: all existing tests still PASS (new optional field with a default cannot break existing `OrderEvent(...)` call sites).

- [ ] **Step 6: Commit**

```bash
git add 04_paper_trading/events.py tests/test_paper_trading_events.py
git commit -m "feat: add OrderEvent.limit_price and SubmittedEvent for US-stocks paper trading"
```

---

### Task 2: `risk_agent.py` — register VOO/QQQ and populate `limit_price` for stock buys

**Files:**
- Modify: `04_paper_trading/agents/risk_agent.py`
- Test: `tests/test_paper_trading_risk_agent.py`

**Interfaces:**
- Consumes: `events.OrderEvent(..., limit_price=...)` from Task 1.
- Produces: `risk_agent.SYMBOL_MARKET_TYPES` now includes `"VOO": "stocks", "QQQ": "stocks"`. `risk_agent.review_portfolio(...)` (signature unchanged) now sets `limit_price` on approved stock buy `OrderEvent`s — later tasks (`run_once_stocks.py`) rely on this to know the LOO price without recomputing it.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_paper_trading_risk_agent.py` (after the existing `test_review_portfolio_approves_buy_when_alone_and_within_limits` test):

```python
def test_symbol_market_types_includes_stock_symbols():
    assert risk_agent.SYMBOL_MARKET_TYPES["VOO"] == "stocks"
    assert risk_agent.SYMBOL_MARKET_TYPES["QQQ"] == "stocks"


def test_review_portfolio_sets_limit_price_on_stock_buy_order():
    signal_events = {
        "VOO": _make_signal_event("VOO", target_position=1, close_price=550.0, average_true_range=5.0)
    }
    close_price_histories = {"VOO": _make_close_price_series([540.0 + index for index in range(30)])}

    decisions = risk_agent.review_portfolio(
        signal_events, {}, {}, 10_000.0, 10_000.0, close_price_histories, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["VOO"], OrderEvent)
    assert decisions["VOO"].quantity == pytest.approx(10.0)  # 0.01*550/(2*5) = 0.55 佔比, 5500/550 = 10 股
    assert decisions["VOO"].limit_price == 550.0


def test_review_portfolio_leaves_limit_price_none_on_crypto_buy_order():
    signal_events = {
        "BTCUSDT": _make_signal_event(
            "BTCUSDT", target_position=1, close_price=50_000.0, average_true_range=1_000.0
        )
    }
    close_price_histories = {
        "BTCUSDT": _make_close_price_series([50_000.0 + index * 100 for index in range(30)])
    }

    decisions = risk_agent.review_portfolio(
        signal_events, {}, {}, 10_000.0, 10_000.0, close_price_histories, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["BTCUSDT"], OrderEvent)
    assert decisions["BTCUSDT"].limit_price is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_paper_trading_risk_agent.py -v -k "symbol_market_types_includes_stock or limit_price"`
Expected: FAIL — `KeyError: 'VOO'` on the first test (not in `SYMBOL_MARKET_TYPES`); `AttributeError` or assertion failure on the other two (`limit_price` doesn't exist yet on results, since `OrderEvent` didn't have it before Task 1 — after Task 1 it exists but defaults to `None` for both, so the VOO test specifically fails on `decisions["VOO"].limit_price == 550.0`).

- [ ] **Step 3: Implement**

In `04_paper_trading/agents/risk_agent.py`, modify the `SYMBOL_MARKET_TYPES` constant:

```python
SYMBOL_MARKET_TYPES = {
    "BTCUSDT": "crypto",
    "ETHUSDT": "crypto",
    "VOO": "stocks",
    "QQQ": "stocks",
}
```

Then find the final block inside `review_portfolio` that constructs the approved buy `OrderEvent` (currently reads `decisions[symbol] = OrderEvent(symbol=symbol, side="BUY", quantity=buy_quantity)` followed by `open_long_symbols.append(symbol)`), and replace it with:

```python
        limit_price = signal_event.latest_close_price if market_type == "stocks" else None
        decisions[symbol] = OrderEvent(
            symbol=symbol, side="BUY", quantity=buy_quantity, limit_price=limit_price
        )
        open_long_symbols.append(symbol)
```

(`market_type` is already in scope at this point in the function — it was assigned a few lines earlier as `market_type = SYMBOL_MARKET_TYPES[symbol]` for the max-concurrent-positions check. No new lookup needed.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_paper_trading_risk_agent.py -v`
Expected: PASS, all tests green (including the pre-existing ones — adding dict entries and an optional field is additive).

- [ ] **Step 5: Run full test suite to confirm no regression**

Run: `pytest tests/ -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add 04_paper_trading/agents/risk_agent.py tests/test_paper_trading_risk_agent.py
git commit -m "feat: register VOO/QQQ as stocks market type and populate OrderEvent.limit_price"
```

---

### Task 3: `alpaca_paper_trading_client.py` — new Alpaca Paper Trading REST client

**Files:**
- Create: `04_paper_trading/alpaca_paper_trading_client.py`
- Test: `tests/test_alpaca_paper_trading_client_rounding.py`

**Interfaces:**
- Consumes: `.env` keys `ALPACA_PAPER_API_KEY`, `ALPACA_PAPER_SECRET_KEY`, `ALPACA_PAPER_BASE_URL` (all three already present in `.env.example` from Phase 0 — no `.env.example` changes needed in this plan).
- Produces (used by later tasks): `get_account() -> dict` (keys `"equity"`, `"cash"`, both `float`), `get_positions() -> dict[str, float]`, `get_todays_calendar_entry(today: str) -> dict | None`, `place_limit_on_open_order(symbol: str, side: str, quantity: int, limit_price: float) -> tuple[int, dict]`, `place_market_on_open_order(symbol: str, side: str, quantity: int) -> tuple[int, dict]`, `round_quantity_down_to_whole_shares(quantity: float) -> int` (pure function).

Per the Global Constraints, only `round_quantity_down_to_whole_shares` gets an automated unit test here — the five networked functions are exercised via `monkeypatch` at their call sites in Tasks 5/6 tests, and manually verified against the real Alpaca sandbox in Task 9 (same convention as `binance_testnet_client.py`, which likewise has no automated test for its networked functions — see `tests/test_binance_testnet_client_rounding.py`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_alpaca_paper_trading_client_rounding.py`:

```python
"""alpaca_paper_trading_client 的純函數單元測試: round_quantity_down_to_whole_shares, 不打真實網路請求"""
import alpaca_paper_trading_client


def test_round_quantity_down_to_whole_shares_truncates_fraction():
    assert alpaca_paper_trading_client.round_quantity_down_to_whole_shares(10.9) == 10


def test_round_quantity_down_to_whole_shares_exact_whole_number_unchanged():
    assert alpaca_paper_trading_client.round_quantity_down_to_whole_shares(7.0) == 7


def test_round_quantity_down_to_whole_shares_below_one_share_becomes_zero():
    assert alpaca_paper_trading_client.round_quantity_down_to_whole_shares(0.5) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_alpaca_paper_trading_client_rounding.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpaca_paper_trading_client'`

- [ ] **Step 3: Implement**

Create `04_paper_trading/alpaca_paper_trading_client.py`:

```python
"""
Alpaca Paper Trading 交易客戶端: 用 API-Key 標頭驗證的 REST 呼叫, 查詢帳戶, 倉位, 交易日曆與下單
與 02_data/fetchers/alpaca_fetcher.py 的行情端點(data.alpaca.markets) 不同, 這裡打的是交易端點
(paper-api.alpaca.markets), 但沿用同一組 .env 憑證(ALPACA_PAPER_API_KEY / ALPACA_PAPER_SECRET_KEY) .
比 Binance 的 HMAC(Hash-based Message Authentication Code) 簽名簡單, 只需固定的兩個標頭, 不需組簽名字串
"""
import os

import requests
from dotenv import load_dotenv

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
_repository_root = os.path.dirname(_paper_trading_directory)
load_dotenv(os.path.join(_repository_root, ".env"))

REQUEST_TIMEOUT_SECONDS = 30


def _get_base_url() -> str:
    """從 .env 讀取交易端點, 缺省時退回 Alpaca Paper Trading 的官方端點"""
    return os.getenv("ALPACA_PAPER_BASE_URL", "https://paper-api.alpaca.markets")


def _build_authentication_headers() -> dict:
    """組出 Alpaca 要求的認證標頭, 缺少憑證時直接報錯提示先設定 .env"""
    api_key = os.getenv("ALPACA_PAPER_API_KEY")
    secret_key = os.getenv("ALPACA_PAPER_SECRET_KEY")
    if not api_key or not secret_key or "your_" in api_key:
        raise RuntimeError(
            "缺少 Alpaca 憑證, 請先在 .env 填入 ALPACA_PAPER_API_KEY 與 ALPACA_PAPER_SECRET_KEY"
        )
    return {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}


def get_account() -> dict:
    """查詢帳戶狀態, 回傳 {"equity": 帳戶總淨值, "cash": 現金餘額}, 皆為 float"""
    response = requests.get(
        f"{_get_base_url()}/v2/account",
        headers=_build_authentication_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    account = response.json()
    return {"equity": float(account["equity"]), "cash": float(account["cash"])}


def get_positions() -> dict:
    """查詢目前持倉, 回傳 {股票代號: 股數}, 只含非零倉位"""
    response = requests.get(
        f"{_get_base_url()}/v2/positions",
        headers=_build_authentication_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    positions = response.json()
    return {position["symbol"]: float(position["qty"]) for position in positions}


def get_todays_calendar_entry(today: str) -> dict | None:
    """
    查詢指定日期(today, 格式 YYYY-MM-DD, 呼叫端應傳入美東時間的日期字串, 見 run_once_stocks.py)
    是否為交易日, 非交易日(週末/假日) 回傳 None
    """
    response = requests.get(
        f"{_get_base_url()}/v2/calendar",
        params={"start": today, "end": today},
        headers=_build_authentication_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    calendar_entries = response.json()
    return calendar_entries[0] if calendar_entries else None


def round_quantity_down_to_whole_shares(quantity: float) -> int:
    """把下單數量向下裁到整數股(本專案不支援分數股), 純函數, 可獨立單元測試"""
    return int(quantity)


def _submit_order(order_payload: dict) -> tuple[int, dict]:
    """對 /v2/orders 送出委託, 回傳 (HTTP 狀態碼, 交易所回應 JSON) , 不拋例外, 由呼叫端判斷成敗"""
    response = requests.post(
        f"{_get_base_url()}/v2/orders",
        json=order_payload,
        headers=_build_authentication_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return response.status_code, response.json()


def place_limit_on_open_order(
    symbol: str, side: str, quantity: int, limit_price: float
) -> tuple[int, dict]:
    """下開盤限價單(limit-on-open, LOO): type=limit, time_in_force=opg, 交易所在次日開盤拍賣時撮合"""
    return _submit_order(
        {
            "symbol": symbol,
            "side": side.lower(),
            "type": "limit",
            "time_in_force": "opg",
            "qty": str(quantity),
            "limit_price": str(limit_price),
        }
    )


def place_market_on_open_order(symbol: str, side: str, quantity: int) -> tuple[int, dict]:
    """下開盤市價單(market-on-open, MOO): type=market, time_in_force=opg, 保證在開盤拍賣成交"""
    return _submit_order(
        {
            "symbol": symbol,
            "side": side.lower(),
            "type": "market",
            "time_in_force": "opg",
            "qty": str(quantity),
        }
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_alpaca_paper_trading_client_rounding.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add 04_paper_trading/alpaca_paper_trading_client.py tests/test_alpaca_paper_trading_client_rounding.py
git commit -m "feat: add Alpaca Paper Trading REST client for US-stocks paper trading"
```

---

### Task 4: `agents/stock_data_agent.py` — fetch latest daily bars for signal generation

**Files:**
- Create: `04_paper_trading/agents/stock_data_agent.py`
- Test: `tests/test_stock_data_agent.py`

**Interfaces:**
- Consumes: `02_data/fetchers/alpaca_fetcher.fetch_full_history_daily_bars(symbol: str, start_date: str = ..., data_feed: str = "iex") -> pd.DataFrame` (existing, unmodified — returns ascending-sorted `open_time, open, high, low, close, volume`).
- Produces: `stock_data_agent.fetch_latest_daily_bars(symbol: str, lookback_bars: int = 100) -> pd.DataFrame` — same shape/contract as the crypto side's `data_agent.fetch_latest_candles`, consumed by `run_once_stocks.py` (Task 6) and `signal_agent.decide` (existing, unmodified).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_stock_data_agent.py`:

```python
"""stock_data_agent.fetch_latest_daily_bars 的單元測試: monkeypatch 掉真實網路請求, 只測組裝與長度檢查邏輯"""
import pandas as pd
import pytest

import stock_data_agent


def _make_ohlcv_dataframe(number_of_rows: int) -> pd.DataFrame:
    base_time = pd.Timestamp("2026-01-01")
    return pd.DataFrame(
        {
            "open_time": [base_time + pd.Timedelta(days=index) for index in range(number_of_rows)],
            "open": [100.0] * number_of_rows,
            "high": [101.0] * number_of_rows,
            "low": [99.0] * number_of_rows,
            "close": [100.0 + index for index in range(number_of_rows)],
            "volume": [1_000_000.0] * number_of_rows,
        }
    )


def test_fetch_latest_daily_bars_returns_last_lookback_bars_rows(monkeypatch):
    recorded_calls = []

    def _fake_fetch_full_history_daily_bars(symbol, start_date=None, data_feed="iex"):
        recorded_calls.append({"symbol": symbol, "start_date": start_date})
        return _make_ohlcv_dataframe(150)

    monkeypatch.setattr(
        stock_data_agent, "fetch_full_history_daily_bars", _fake_fetch_full_history_daily_bars
    )

    ohlcv_dataframe = stock_data_agent.fetch_latest_daily_bars("VOO", lookback_bars=100)

    assert len(ohlcv_dataframe) == 100
    assert list(ohlcv_dataframe.columns) == ["open_time", "open", "high", "low", "close", "volume"]
    # 保留的必須是最後 100 根(最新的), 不是前 100 根
    assert ohlcv_dataframe["close"].iloc[-1] == 100.0 + 149
    assert recorded_calls[0]["symbol"] == "VOO"


def test_fetch_latest_daily_bars_raises_when_insufficient_bars(monkeypatch):
    def _fake_fetch_full_history_daily_bars(symbol, start_date=None, data_feed="iex"):
        return _make_ohlcv_dataframe(5)

    monkeypatch.setattr(
        stock_data_agent, "fetch_full_history_daily_bars", _fake_fetch_full_history_daily_bars
    )

    with pytest.raises(ValueError, match="少於暖身所需"):
        stock_data_agent.fetch_latest_daily_bars("VOO", lookback_bars=100)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stock_data_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stock_data_agent'`

- [ ] **Step 3: Implement**

Create `04_paper_trading/agents/stock_data_agent.py`:

```python
"""
Stock data agent: 拉取最新美股日線, 供 signal_agent 產生即時信號用.
重用 02_data/fetchers/alpaca_fetcher.py 的 fetch_full_history_daily_bars(已測試過的抓取邏輯), 以
今天往回推 LOOKBACK_CALENDAR_DAYS 個日曆天當 start_date, 取回後只保留最後 lookback_bars 根,
不重寫一套抓取邏輯, 與加密貨幣側 data_agent.py 重用既有抓取程式碼路徑的精神一致.
"""
import os
import sys
from datetime import date, timedelta

import pandas as pd

_agents_directory = os.path.dirname(os.path.abspath(__file__))
_paper_trading_directory = os.path.dirname(_agents_directory)
_repository_root = os.path.dirname(_paper_trading_directory)
sys.path.insert(0, os.path.join(_repository_root, "02_data", "fetchers"))
from alpaca_fetcher import fetch_full_history_daily_bars  # noqa: E402

# 暖身期保守值, 與加密貨幣側 data_agent.DEFAULT_LOOKBACK_BARS 同一套理由:
# exp_002 的 slow_span=26 / adx_period=14 皆為威爾德式平滑(Wilder smoothing), 100 根後殘餘權重
# 已降到千分之一以下, 讓即時計算的指標值更貼近回測用全歷史算出的版本
DEFAULT_LOOKBACK_BARS = 100
# 100 個交易日約需回推 140 個日曆天(週末/假日不開盤); 200 天留了充足緩衝, 確保抓得到足夠根數
LOOKBACK_CALENDAR_DAYS = 200


def fetch_latest_daily_bars(symbol: str, lookback_bars: int = DEFAULT_LOOKBACK_BARS) -> pd.DataFrame:
    """
    拉取最近 lookback_bars 根已收盤日線, 足夠 exp_002 策略指標暖身
    回傳按時間升冪排列, 只含核心 OHLCV(開高低收量) 欄位的 DataFrame
    拋出 ValueError: 若抓到的根數少於 lookback_bars(數據不足, 不該在殘缺窗口上硬算指標)
    """
    start_date = (date.today() - timedelta(days=LOOKBACK_CALENDAR_DAYS)).isoformat()
    ohlcv_dataframe = fetch_full_history_daily_bars(symbol, start_date=start_date)
    if len(ohlcv_dataframe) < lookback_bars:
        raise ValueError(
            f"{symbol} 只抓到 {len(ohlcv_dataframe)} 根已收盤日線, "
            f"少於暖身所需的 {lookback_bars} 根"
        )
    return ohlcv_dataframe.tail(lookback_bars).reset_index(drop=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stock_data_agent.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add 04_paper_trading/agents/stock_data_agent.py tests/test_stock_data_agent.py
git commit -m "feat: add stock_data_agent for US-stocks paper trading"
```

---

### Task 5: `agents/stock_execution_agent.py` — submit LOO/MOO orders to Alpaca

**Files:**
- Create: `04_paper_trading/agents/stock_execution_agent.py`
- Test: `tests/test_stock_execution_agent.py`

**Interfaces:**
- Consumes: `events.OrderEvent` (Task 1), `events.FailEvent` (existing), `events.SubmittedEvent` (Task 1), `alpaca_paper_trading_client.place_limit_on_open_order`, `.place_market_on_open_order`, `.round_quantity_down_to_whole_shares` (Task 3).
- Produces: `stock_execution_agent.execute(order_event: OrderEvent) -> SubmittedEvent | FailEvent` — consumed by `run_once_stocks.py` (Task 6).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_stock_execution_agent.py`:

```python
"""stock_execution_agent.execute 的單元測試: monkeypatch 掉 alpaca_paper_trading_client 的真實網路呼叫"""
import pytest
import requests

import stock_execution_agent
from events import FailEvent, OrderEvent, SubmittedEvent


def test_execute_submits_limit_on_open_order_for_buy(monkeypatch):
    order_event = OrderEvent(symbol="VOO", side="BUY", quantity=10.0, limit_price=550.25)
    recorded_calls = []

    def _fake_place_limit_on_open_order(symbol, side, quantity, limit_price):
        recorded_calls.append((symbol, side, quantity, limit_price))
        return 200, {"id": "order-1", "status": "accepted"}

    monkeypatch.setattr(
        stock_execution_agent, "place_limit_on_open_order", _fake_place_limit_on_open_order
    )

    result = stock_execution_agent.execute(order_event)

    assert isinstance(result, SubmittedEvent)
    assert result.symbol == "VOO"
    assert result.side == "BUY"
    assert result.order_id == "order-1"
    assert result.limit_price == 550.25
    assert recorded_calls == [("VOO", "BUY", 10, 550.25)]


def test_execute_submits_market_on_open_order_for_sell(monkeypatch):
    order_event = OrderEvent(symbol="VOO", side="SELL", quantity=10.0)
    recorded_calls = []

    def _fake_place_market_on_open_order(symbol, side, quantity):
        recorded_calls.append((symbol, side, quantity))
        return 200, {"id": "order-2", "status": "accepted"}

    monkeypatch.setattr(
        stock_execution_agent, "place_market_on_open_order", _fake_place_market_on_open_order
    )

    result = stock_execution_agent.execute(order_event)

    assert isinstance(result, SubmittedEvent)
    assert result.order_id == "order-2"
    assert result.limit_price is None
    assert recorded_calls == [("VOO", "SELL", 10)]


def test_execute_returns_fail_event_when_rounded_quantity_is_zero():
    order_event = OrderEvent(symbol="VOO", side="BUY", quantity=0.5, limit_price=550.0)

    result = stock_execution_agent.execute(order_event)

    assert isinstance(result, FailEvent)
    assert "整數股" in result.reason


def test_execute_returns_fail_event_when_exchange_rejects_order(monkeypatch):
    order_event = OrderEvent(symbol="VOO", side="BUY", quantity=10.0, limit_price=550.25)
    monkeypatch.setattr(
        stock_execution_agent,
        "place_limit_on_open_order",
        lambda symbol, side, quantity, limit_price: (422, {"message": "insufficient buying power"}),
    )

    result = stock_execution_agent.execute(order_event)

    assert isinstance(result, FailEvent)
    assert "insufficient buying power" in result.reason


def test_execute_returns_fail_event_when_place_order_raises_network_exception(monkeypatch):
    order_event = OrderEvent(symbol="VOO", side="BUY", quantity=10.0, limit_price=550.25)

    def _raise_connection_error(symbol, side, quantity, limit_price):
        raise requests.exceptions.ConnectionError("模擬連線逾時")

    monkeypatch.setattr(stock_execution_agent, "place_limit_on_open_order", _raise_connection_error)

    result = stock_execution_agent.execute(order_event)

    assert isinstance(result, FailEvent)
    assert "網路例外" in result.reason
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_stock_execution_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stock_execution_agent'`

- [ ] **Step 3: Implement**

Create `04_paper_trading/agents/stock_execution_agent.py`:

```python
"""
Stock execution agent: 把核准的 OrderEvent 轉成真實 Alpaca Paper Trading 開盤委託單.
買進用開盤限價單(limit-on-open, LOO, 限價 = 收盤時算出的價格), 賣出(出場) 用開盤市價單
(market-on-open, MOO): 出場的目的是降低風險曝險, 保證成交比價格保護更重要, 見設計文件說明.
委託送出時市場尚未開盤, 不會立即成交, 回傳 SubmittedEvent(已送出, 未確認成交) 而非 FillEvent,
成交與否留給次日執行時查詢真實倉位自然核對(見設計文件的次日的自然核對機制段落).
"""
import os
import sys

import requests

from alpaca_paper_trading_client import (
    place_limit_on_open_order,
    place_market_on_open_order,
    round_quantity_down_to_whole_shares,
)

_agents_directory = os.path.dirname(os.path.abspath(__file__))
_paper_trading_directory = os.path.dirname(_agents_directory)
sys.path.insert(0, _paper_trading_directory)

from events import FailEvent, OrderEvent, SubmittedEvent  # noqa: E402


def execute(order_event: OrderEvent) -> SubmittedEvent | FailEvent:
    """
    把核准的 OrderEvent 轉成 Alpaca 開盤委託單; 買進用限價(LOO), 賣出用市價(MOO)
    數量先向下裁到整數股(不支援分數股), 裁剪後為 0 直接回報失敗, 不送出空單
    """
    rounded_quantity = round_quantity_down_to_whole_shares(order_event.quantity)
    if rounded_quantity <= 0:
        return FailEvent(
            symbol=order_event.symbol,
            reason="裁剪至整數股後數量為 0, 部位過小無法下單",
            raw_exchange_response="",
        )

    try:
        if order_event.side == "BUY":
            status_code, order_response = place_limit_on_open_order(
                order_event.symbol, order_event.side, rounded_quantity, order_event.limit_price
            )
        else:
            status_code, order_response = place_market_on_open_order(
                order_event.symbol, order_event.side, rounded_quantity
            )
    except requests.exceptions.RequestException as network_error:
        # 下單請求本身發生網路例外: 無法得知委託是否已送達交易所, 不能盲目重送(可能造成重複下單)
        return FailEvent(
            symbol=order_event.symbol,
            reason=f"下單請求發生網路例外, 無法確認委託是否已送達交易所, 需人工核對: {network_error}",
            raw_exchange_response="",
        )

    if status_code not in (200, 201):
        return FailEvent(
            symbol=order_event.symbol,
            reason=order_response.get("message", f"下單失敗, HTTP {status_code}"),
            raw_exchange_response=str(order_response),
        )

    return SubmittedEvent(
        symbol=order_event.symbol,
        side=order_event.side,
        quantity=float(rounded_quantity),
        order_id=str(order_response["id"]),
        limit_price=order_event.limit_price,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_stock_execution_agent.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add 04_paper_trading/agents/stock_execution_agent.py tests/test_stock_execution_agent.py
git commit -m "feat: add stock_execution_agent submitting LOO/MOO orders to Alpaca"
```

---

### Task 6: `run_once_stocks.py` — orchestrate the daily US-stocks pipeline

**Files:**
- Create: `04_paper_trading/run_once_stocks.py`
- Test: `tests/test_run_once_stocks.py`

**Interfaces:**
- Consumes: `alpaca_paper_trading_client.get_account/.get_positions/.get_todays_calendar_entry` (Task 3), `stock_data_agent.fetch_latest_daily_bars` (Task 4), `stock_execution_agent.execute` (Task 5), `signal_agent.decide` / `signal_agent.FROZEN_ENGINE_PARAMETERS` (existing, unmodified), `risk_agent.review_portfolio` / `.check_data_staleness` / `.compute_staleness_detail` / `.check_daily_circuit_breaker` (existing + Task 2), `daily_risk_state.load_daily_state` / `.save_daily_state` / `.should_reset_for_new_day` (existing, unmodified), `telegram_alerts.send_alert` (existing, unmodified).
- Produces: `run_once_stocks.run_once(symbols: list = None) -> dict` — the record dict has keys `run_started_at, market_date_eastern, market_open, symbols` always, plus `account_equity_usd, day_start_equity_usd, risk_limits, engine_parameters, fetch_failures, stale_symbols, circuit_breaker_triggered` when `market_open` is `True`. Consumed by `scheduler_stocks.py` (Task 7) and read back from `logs/run_log_stocks.jsonl` by `monitor_stocks.py` (Task 8) — the `market_date_eastern` key is what `monitor_stocks.py` filters on, not UTC date.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_run_once_stocks.py`:

```python
"""run_once_stocks.py 的編排邏輯測試: monkeypatch 掉所有 agent 與外部狀態, 只驗證串接順序與紀錄格式正確"""
from datetime import datetime, timezone

import pandas as pd
import pytest

import run_once_stocks
from events import OrderEvent, SignalEvent, SubmittedEvent


def _make_ohlcv_dataframe():
    current_time = pd.Timestamp.now(tz="UTC").tz_localize(None)
    return pd.DataFrame(
        {
            "open_time": [current_time],
            "open": [550.0],
            "high": [551.0],
            "low": [549.0],
            "close": [550.0],
            "volume": [1_000_000.0],
        }
    )


def _make_signal_event(symbol: str, target_position: int) -> SignalEvent:
    return SignalEvent(
        symbol=symbol,
        target_position=target_position,
        as_of_timestamp=datetime(2026, 7, 10, tzinfo=timezone.utc),
        latest_close_price=550.0,
        latest_average_true_range=5.0,
    )


def _patch_common(monkeypatch, tmp_path):
    """幾乎每個測試都需要的共用 monkeypatch: 記錄檔與每日狀態檔路徑指到 tmp_path, 攔截 Telegram 警報,
    並預設今天是交易日(個別測試需要非交易日情境時再自行覆寫)"""
    monkeypatch.setattr(run_once_stocks, "LOG_FILE_PATH", str(tmp_path / "run_log_stocks.jsonl"))
    monkeypatch.setattr(
        run_once_stocks, "DAILY_STATE_FILE_PATH", str(tmp_path / "daily_risk_state_stocks.json")
    )
    monkeypatch.setattr(run_once_stocks.telegram_alerts, "send_alert", lambda message: None)
    monkeypatch.setattr(
        run_once_stocks.alpaca_paper_trading_client,
        "get_todays_calendar_entry",
        lambda today: {"date": today, "open": "09:30", "close": "16:00"},
    )


def test_run_once_records_market_closed_as_no_op_without_fetching_data(tmp_path, monkeypatch):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        run_once_stocks.alpaca_paper_trading_client, "get_todays_calendar_entry", lambda today: None
    )
    fetch_calls = []
    monkeypatch.setattr(
        run_once_stocks.stock_data_agent,
        "fetch_latest_daily_bars",
        lambda symbol: fetch_calls.append(symbol) or _make_ohlcv_dataframe(),
    )

    record = run_once_stocks.run_once(symbols=["VOO"])

    assert record["market_open"] is False
    assert fetch_calls == []
    assert record["symbols"] == {}


def test_run_once_logs_no_action_when_risk_agent_returns_none(tmp_path, monkeypatch):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        run_once_stocks.stock_data_agent,
        "fetch_latest_daily_bars",
        lambda symbol: _make_ohlcv_dataframe(),
    )
    monkeypatch.setattr(
        run_once_stocks.signal_agent,
        "decide",
        lambda ohlcv_dataframe, symbol: _make_signal_event(symbol, 0),
    )
    monkeypatch.setattr(
        run_once_stocks.alpaca_paper_trading_client,
        "get_account",
        lambda: {"equity": 10_000.0, "cash": 10_000.0},
    )
    monkeypatch.setattr(run_once_stocks.alpaca_paper_trading_client, "get_positions", lambda: {})
    monkeypatch.setattr(
        run_once_stocks.risk_agent, "review_portfolio", lambda *args, **kwargs: {"VOO": None}
    )

    record = run_once_stocks.run_once(symbols=["VOO"])

    assert record["market_open"] is True
    assert record["symbols"]["VOO"]["risk_decision"]["type"] == "NoActionNeeded"
    assert record["symbols"]["VOO"]["execution_result"] is None


def test_run_once_submits_order_when_risk_agent_approves(tmp_path, monkeypatch):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        run_once_stocks.stock_data_agent,
        "fetch_latest_daily_bars",
        lambda symbol: _make_ohlcv_dataframe(),
    )
    monkeypatch.setattr(
        run_once_stocks.signal_agent,
        "decide",
        lambda ohlcv_dataframe, symbol: _make_signal_event(symbol, 1),
    )
    monkeypatch.setattr(
        run_once_stocks.alpaca_paper_trading_client,
        "get_account",
        lambda: {"equity": 10_000.0, "cash": 10_000.0},
    )
    monkeypatch.setattr(run_once_stocks.alpaca_paper_trading_client, "get_positions", lambda: {})
    approved_order = OrderEvent(symbol="VOO", side="BUY", quantity=10.0, limit_price=550.0)
    monkeypatch.setattr(
        run_once_stocks.risk_agent, "review_portfolio", lambda *args, **kwargs: {"VOO": approved_order}
    )
    submitted_event = SubmittedEvent(
        symbol="VOO", side="BUY", quantity=10.0, order_id="order-1", limit_price=550.0
    )
    monkeypatch.setattr(
        run_once_stocks.stock_execution_agent, "execute", lambda order_event: submitted_event
    )

    record = run_once_stocks.run_once(symbols=["VOO"])

    assert record["symbols"]["VOO"]["risk_decision"]["type"] == "OrderEvent"
    assert record["symbols"]["VOO"]["execution_result"]["type"] == "SubmittedEvent"
    assert record["symbols"]["VOO"]["execution_result"]["order_id"] == "order-1"


def test_run_once_records_fetch_failure_without_aborting_other_symbols(tmp_path, monkeypatch):
    _patch_common(monkeypatch, tmp_path)

    def _fetch_latest_daily_bars(symbol):
        if symbol == "VOO":
            raise ConnectionError("模擬網路逾時")
        return _make_ohlcv_dataframe()

    monkeypatch.setattr(
        run_once_stocks.stock_data_agent, "fetch_latest_daily_bars", _fetch_latest_daily_bars
    )
    monkeypatch.setattr(
        run_once_stocks.signal_agent,
        "decide",
        lambda ohlcv_dataframe, symbol: _make_signal_event(symbol, 0),
    )
    monkeypatch.setattr(
        run_once_stocks.alpaca_paper_trading_client,
        "get_account",
        lambda: {"equity": 10_000.0, "cash": 10_000.0},
    )
    monkeypatch.setattr(run_once_stocks.alpaca_paper_trading_client, "get_positions", lambda: {})
    monkeypatch.setattr(
        run_once_stocks.risk_agent, "review_portfolio", lambda *args, **kwargs: {"QQQ": None}
    )

    record = run_once_stocks.run_once(symbols=["VOO", "QQQ"])

    assert "模擬網路逾時" in record["fetch_failures"]["VOO"]
    assert "VOO" not in record["symbols"]
    assert record["symbols"]["QQQ"]["risk_decision"]["type"] == "NoActionNeeded"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_run_once_stocks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'run_once_stocks'`

- [ ] **Step 3: Implement**

Create `04_paper_trading/run_once_stocks.py`:

```python
"""
Phase 3 紙上交易 (paper trading) 美股執行腳本: 對 VOO 與 QQQ 兩個標的一次執行.
資料流程依序是 data, signal, risk, execution. 與加密貨幣側 run_once.py 架構相同, 差異只在資料來源/執行客戶端
換成 Alpaca, 且核准的開倉單一律走開盤限價/市價委託(limit-on-open / market-on-open), 不做立即市價單.
開頭先檢查今天是否為美股交易日(用美東時間計算, 不依賴伺服器本地時區, 見 US_EASTERN_TIMEZONE),
非交易日安靜跳過, 不產生信號也不查帳戶.
用法: python run_once_stocks.py
"""
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)
sys.path.insert(0, os.path.join(_paper_trading_directory, "agents"))

import alpaca_paper_trading_client  # noqa: E402
import daily_risk_state  # noqa: E402
import risk_agent  # noqa: E402
import signal_agent  # noqa: E402
import stock_data_agent  # noqa: E402
import stock_execution_agent  # noqa: E402
import telegram_alerts  # noqa: E402
from events import OrderEvent  # noqa: E402

SYMBOLS = ["VOO", "QQQ"]
BAR_INTERVAL = timedelta(days=1)
LOG_FILE_PATH = os.path.join(_paper_trading_directory, "logs", "run_log_stocks.jsonl")
DAILY_STATE_FILE_PATH = os.path.join(
    _paper_trading_directory, "logs", "daily_risk_state_stocks.json"
)
# 用美東時間(而非伺服器本地時區) 判斷今天是哪個交易日: 伺服器在 Asia/Hong_Kong, 收盤後(美東 16:35)
# 執行時, 香港當地已跨到隔天, 若用伺服器本地日期查交易日曆會查錯日期; zoneinfo 自動處理夏令/冬令時間轉換
US_EASTERN_TIMEZONE = ZoneInfo("America/New_York")

RISK_LIMITS = {
    "max_loss_per_trade_fraction": 0.015,
    "max_daily_loss_fraction": 0.04,
    "max_positions_by_market": {"crypto": 3, "stocks": 5},
    "max_correlation": 0.8,
}


def _serialize_event(event) -> dict:
    """把 dataclass 事件轉成可寫入 JSON 的字典; 無事件(None, 代表無需動作) 轉成明確標記"""
    if event is None:
        return {"type": "NoActionNeeded"}
    serialized = asdict(event)
    serialized["type"] = type(event).__name__
    return serialized


def _append_log_record(record: dict) -> None:
    """把這次執行紀錄追加寫入 logs/run_log_stocks.jsonl(一行一筆 JSON, gitignore 排除) """
    os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)
    with open(LOG_FILE_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")


def run_once(symbols: list = None) -> dict:
    """
    跑一次完整美股 pipeline: 先確認今天是美股交易日, 再對每個標的收集 data/signal, 交給 risk_agent
    一次性做 portfolio 決策, 核准的開倉單一律送開盤限價/市價委託(LOO/MOO), 不嘗試確認即時成交
    (委託送出時市場尚未開盤); 成交與否由次日執行時查詢真實倉位自然核對
    """
    symbols = symbols if symbols is not None else SYMBOLS
    today_eastern = datetime.now(US_EASTERN_TIMEZONE).date().isoformat()
    record = {
        "run_started_at": datetime.now(timezone.utc).isoformat(),
        "market_date_eastern": today_eastern,
        "symbols": {},
    }

    calendar_entry = alpaca_paper_trading_client.get_todays_calendar_entry(today_eastern)
    if calendar_entry is None:
        record["market_open"] = False
        _append_log_record(record)
        return record
    record["market_open"] = True

    daily_state = daily_risk_state.load_daily_state(DAILY_STATE_FILE_PATH)
    account = alpaca_paper_trading_client.get_account()
    current_positions = alpaca_paper_trading_client.get_positions()

    signal_events = {}
    stale_symbols = {}
    close_price_histories = {}
    fetch_failures = {}

    for symbol in symbols:
        try:
            ohlcv_dataframe = stock_data_agent.fetch_latest_daily_bars(symbol)
        except Exception as fetch_error:
            fetch_failures[symbol] = str(fetch_error)
            continue

        close_price_histories[symbol] = ohlcv_dataframe["close"]
        last_candle_open_time = (
            ohlcv_dataframe["open_time"].iloc[-1].to_pydatetime().replace(tzinfo=timezone.utc)
        )
        current_time = datetime.now(timezone.utc)
        is_fresh = risk_agent.check_data_staleness(last_candle_open_time, current_time, BAR_INTERVAL)
        if not is_fresh:
            stale_symbols[symbol] = risk_agent.compute_staleness_detail(
                last_candle_open_time, current_time, BAR_INTERVAL
            )
            continue

        signal_events[symbol] = signal_agent.decide(ohlcv_dataframe, symbol)

    account_equity_usd = account["equity"]
    current_share_balances = {
        symbol: current_positions.get(symbol, 0.0) for symbol in signal_events
    }

    if daily_risk_state.should_reset_for_new_day(
        daily_state.get("market_date_eastern"), today_eastern
    ):
        daily_state = {
            "market_date_eastern": today_eastern,
            "equity_at_day_start_usd": account_equity_usd,
        }
        daily_risk_state.save_daily_state(DAILY_STATE_FILE_PATH, daily_state)
    day_start_equity_usd = daily_state["equity_at_day_start_usd"]

    record["account_equity_usd"] = account_equity_usd
    record["day_start_equity_usd"] = day_start_equity_usd
    record["risk_limits"] = RISK_LIMITS
    record["engine_parameters"] = signal_agent.FROZEN_ENGINE_PARAMETERS
    record["fetch_failures"] = fetch_failures
    record["stale_symbols"] = stale_symbols

    circuit_breaker_triggered = not risk_agent.check_daily_circuit_breaker(
        account_equity_usd, day_start_equity_usd, RISK_LIMITS["max_daily_loss_fraction"]
    )
    record["circuit_breaker_triggered"] = circuit_breaker_triggered
    if circuit_breaker_triggered:
        telegram_alerts.send_alert(
            f"[美股] 每日虧損熔斷已觸發: 帳戶淨值從 {day_start_equity_usd:.2f} USD "
            f"降至 {account_equity_usd:.2f} USD, 停止今日所有交易"
        )
    if stale_symbols:
        telegram_alerts.send_alert(f"[美股] 數據異常保護觸發, 暫停信號生成: {', '.join(stale_symbols)}")

    decisions = risk_agent.review_portfolio(
        signal_events,
        stale_symbols,
        current_share_balances,
        account_equity_usd,
        day_start_equity_usd,
        close_price_histories,
        signal_agent.FROZEN_ENGINE_PARAMETERS,
        RISK_LIMITS,
    )

    for symbol, decision in decisions.items():
        symbol_record = {"risk_decision": _serialize_event(decision)}
        if symbol in signal_events:
            signal_event = signal_events[symbol]
            symbol_record["signal"] = {
                "target_position": signal_event.target_position,
                "latest_close_price": signal_event.latest_close_price,
                "latest_average_true_range": signal_event.latest_average_true_range,
                "as_of_timestamp": signal_event.as_of_timestamp,
            }
            symbol_record["current_share_balance"] = current_share_balances[symbol]
        if isinstance(decision, OrderEvent):
            execution_result = stock_execution_agent.execute(decision)
            symbol_record["execution_result"] = _serialize_event(execution_result)
        else:
            symbol_record["execution_result"] = None
        record["symbols"][symbol] = symbol_record

    _append_log_record(record)
    return record


def main() -> None:
    try:
        record = run_once()
    except Exception as error:
        print(f"執行失敗: {error}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(record, indent=2, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_run_once_stocks.py -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite to confirm no regression**

Run: `pytest tests/ -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add 04_paper_trading/run_once_stocks.py tests/test_run_once_stocks.py
git commit -m "feat: add run_once_stocks orchestrating the daily US-stocks pipeline"
```

---

### Task 7: `scheduler_stocks.py` — lock, run, and summarize once a day

**Files:**
- Create: `04_paper_trading/scheduler_stocks.py`
- Test: `tests/test_scheduler_stocks.py`

**Interfaces:**
- Consumes: `run_once_stocks.run_once() -> dict` (Task 6), `telegram_alerts.send_alert` (existing).
- Produces: `scheduler_stocks.run_scheduled(lock_file_path: str) -> dict`, `scheduler_stocks.main() -> None` (calls `sys.exit`), `scheduler_stocks.SchedulerLockedError`, `scheduler_stocks._format_run_summary(record: dict) -> str` — same public shape as the crypto side's `scheduler.py`, used only by crontab, no downstream task depends on these beyond the tests.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scheduler_stocks.py`:

```python
"""scheduler_stocks.py 的排程安全網測試 : 鎖行為與告警分流全程 mock, 不碰真正鎖檔或外部網路"""
import fcntl

import pytest

import scheduler_stocks


def test_format_run_summary_reports_submitted_order():
    record = {
        "run_started_at": "2026-07-10T20:35:00+00:00",
        "symbols": {
            "VOO": {
                "risk_decision": {"type": "OrderEvent", "symbol": "VOO", "side": "BUY", "quantity": 10.0},
                "execution_result": {
                    "type": "SubmittedEvent", "symbol": "VOO", "side": "BUY", "quantity": 10.0,
                    "order_id": "order-1", "limit_price": 550.25,
                },
            },
            "QQQ": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None},
        },
    }

    summary = scheduler_stocks._format_run_summary(record)

    assert "VOO: 買入 10.0 股委託已送出 (order_id=order-1), 待次日開盤確認成交" in summary
    assert "QQQ: 本次無動作" in summary


def test_format_run_summary_reports_rejection_reason_and_values():
    record = {
        "run_started_at": "2026-07-10T20:35:00+00:00",
        "symbols": {
            "QQQ": {
                "risk_decision": {
                    "type": "RejectionEvent", "symbol": "QQQ", "reason": "correlation_exceeds_limit",
                    "computed_value": 0.87, "limit_value": 0.8,
                },
                "execution_result": None,
            },
        },
    }

    summary = scheduler_stocks._format_run_summary(record)

    assert "QQQ: 交易被風控擋下 (correlation_exceeds_limit, 實際值=0.87, 上限=0.8)" in summary


def test_run_scheduled_calls_run_once_when_lock_available(tmp_path, monkeypatch):
    lock_file_path = str(tmp_path / "scheduler_stocks.lock")
    call_count = {"n": 0}

    def _fake_run_once():
        call_count["n"] += 1
        return {"symbols": {}, "market_open": False}

    monkeypatch.setattr(scheduler_stocks.run_once_stocks, "run_once", _fake_run_once)

    result = scheduler_stocks.run_scheduled(lock_file_path)

    assert call_count["n"] == 1
    assert result == {"symbols": {}, "market_open": False}


def test_run_scheduled_raises_when_lock_already_held(tmp_path, monkeypatch):
    lock_file_path = str(tmp_path / "scheduler_stocks.lock")
    holder_file = open(lock_file_path, "w")
    fcntl.flock(holder_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        was_called = {"called": False}
        monkeypatch.setattr(
            scheduler_stocks.run_once_stocks, "run_once", lambda: was_called.update(called=True)
        )

        with pytest.raises(scheduler_stocks.SchedulerLockedError):
            scheduler_stocks.run_scheduled(lock_file_path)

        assert was_called["called"] is False
    finally:
        holder_file.close()


def test_main_skips_summary_when_market_closed(monkeypatch):
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


def test_main_sends_summary_alert_and_exits_zero_when_market_open(monkeypatch):
    fake_record = {
        "run_started_at": "2026-07-10T20:35:00+00:00",
        "market_open": True,
        "symbols": {"VOO": {"risk_decision": {"type": "NoActionNeeded"}, "execution_result": None}},
    }
    monkeypatch.setattr(scheduler_stocks, "run_scheduled", lambda lock_file_path: fake_record)
    alerts = []
    monkeypatch.setattr(
        scheduler_stocks.telegram_alerts, "send_alert", lambda message: alerts.append(message)
    )

    with pytest.raises(SystemExit) as exit_info:
        scheduler_stocks.main()

    assert exit_info.value.code == 0
    assert len(alerts) == 1


def test_main_sends_alert_and_exits_zero_when_locked(monkeypatch):
    def _raise_locked(lock_file_path):
        raise scheduler_stocks.SchedulerLockedError("鎖仍被持有")

    monkeypatch.setattr(scheduler_stocks, "run_scheduled", _raise_locked)
    alerts = []
    monkeypatch.setattr(
        scheduler_stocks.telegram_alerts, "send_alert", lambda message: alerts.append(message)
    )

    with pytest.raises(SystemExit) as exit_info:
        scheduler_stocks.main()

    assert exit_info.value.code == 0
    assert len(alerts) == 1
    assert "尚未結束" in alerts[0]


def test_main_sends_alert_and_exits_one_when_run_once_raises(monkeypatch):
    def _raise_unexpected(lock_file_path):
        raise RuntimeError("模擬 API 無回應")

    monkeypatch.setattr(scheduler_stocks, "run_scheduled", _raise_unexpected)
    alerts = []
    monkeypatch.setattr(
        scheduler_stocks.telegram_alerts, "send_alert", lambda message: alerts.append(message)
    )

    with pytest.raises(SystemExit) as exit_info:
        scheduler_stocks.main()

    assert exit_info.value.code == 1
    assert len(alerts) == 1
    assert "模擬 API 無回應" in alerts[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scheduler_stocks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scheduler_stocks'`

- [ ] **Step 3: Implement**

Create `04_paper_trading/scheduler_stocks.py`:

```python
"""
Phase 3 紙上交易 (paper trading) 美股排程器 (scheduler): 包住 run_once_stocks.run_once() 的排程
安全網, 提供防重疊執行的鎖(lock) 與失敗告警, 讓 crontab 可以無人值守地在每個美股交易日收盤後觸發一次.
非交易日(run_once_stocks 回報 market_open=False) 不發送 Telegram 摘要, 避免週末/假日連續洗版
見設計文件 docs/superpowers/specs/2026-07-10-phase3-us-stocks-paper-trading-design.md
用法: python3 scheduler_stocks.py
"""
import fcntl
import os
import sys
import traceback

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)

import run_once_stocks  # noqa: E402
import telegram_alerts  # noqa: E402

SCHEDULER_LOCK_PATH = os.path.join(_paper_trading_directory, "logs", "scheduler_stocks.lock")
NOTIFY_RUN_SUMMARY = True  # 交易日執行完成後是否發送 Telegram 執行摘要, 設為 False 可關閉此通知


class SchedulerLockedError(Exception):
    """上一次排程執行尚未結束 (鎖仍被持有), 本次應跳過, 不與上一次併發執行"""


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
    if execution_result["type"] == "SubmittedEvent":
        side_label = "買入" if execution_result["side"] == "BUY" else "賣出"
        return (
            f"{symbol}: {side_label} {execution_result['quantity']} 股委託已送出 "
            f"(order_id={execution_result['order_id']}), 待次日開盤確認成交"
        )
    return f"{symbol}: 下單失敗 ({execution_result['reason']})"


def _format_run_summary(record: dict) -> str:
    """把 run_once_stocks.run_once() 回傳的 record 轉成人類可讀的執行摘要"""
    symbol_records = record["symbols"]
    header_line = f"美股 Paper trading 執行摘要 ({record['run_started_at']})"
    symbol_lines = [
        _format_symbol_line(symbol, symbol_record)
        for symbol, symbol_record in symbol_records.items()
    ]
    return "\n".join([header_line, ""] + symbol_lines)


def run_scheduled(lock_file_path: str) -> dict:
    """
    以 fcntl.flock(LOCK_EX | LOCK_NB) 對 lock_file_path 嘗試取得非阻塞的獨占鎖, 取得鎖時呼叫
    run_once_stocks.run_once() 並回傳其結果; 搶不到鎖時拋出 SchedulerLockedError
    """
    os.makedirs(os.path.dirname(lock_file_path), exist_ok=True)
    lock_file = open(lock_file_path, "w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        raise SchedulerLockedError(f"排程鎖 {lock_file_path} 已被持有, 上一次執行可能尚未結束")
    return run_once_stocks.run_once()


def main() -> None:
    try:
        record = run_scheduled(SCHEDULER_LOCK_PATH)
    except SchedulerLockedError as locked_error:
        telegram_alerts.send_alert("[美股] 排程跳過: 上一次執行尚未結束")
        print(str(locked_error), file=sys.stderr)
        sys.exit(0)
    except Exception as error:
        telegram_alerts.send_alert(f"[美股] 排程執行失敗: {error}")
        traceback.print_exc()
        sys.exit(1)
    if not record.get("market_open", True):
        print("今天非美股交易日, 無需執行")
        sys.exit(0)
    if NOTIFY_RUN_SUMMARY:
        telegram_alerts.send_alert(_format_run_summary(record))
    print(f"排程執行完成, 處理標的數: {len(record['symbols'])}")
    sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scheduler_stocks.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add 04_paper_trading/scheduler_stocks.py tests/test_scheduler_stocks.py
git commit -m "feat: add scheduler_stocks with lock, no-op skip, and Telegram summary"
```

---

### Task 8: `monitor_stocks.py` — daily report for the US-stocks pipeline

**Files:**
- Create: `04_paper_trading/monitor_stocks.py`
- Test: `tests/test_monitor_stocks.py`

**Interfaces:**
- Consumes: `logs/run_log_stocks.jsonl` records as produced by `run_once_stocks.py` (Task 6) — specifically the `market_date_eastern`, `market_open`, `account_equity_usd`, `day_start_equity_usd`, `stale_symbols`, `circuit_breaker_triggered`, `symbols` keys. `telegram_alerts.send_alert` (existing).
- Produces: `monitor_stocks._load_records_for_date`, `monitor_stocks._format_daily_report`, `monitor_stocks.main`, `monitor_stocks.US_EASTERN_TIMEZONE` — used only by crontab and tests, no downstream task depends on these.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_monitor_stocks.py`:

```python
"""monitor_stocks.py 的每日報告測試 : 讀檔/日期過濾用 tmp_path, 格式化與發送用手造資料或 mock"""
import json
from datetime import date, datetime, timedelta

import pytest

import monitor_stocks


def test_load_records_for_date_filters_by_market_date_eastern(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    record_before = {"market_date_eastern": "2026-07-09", "marker": "yesterday"}
    record_after = {"market_date_eastern": "2026-07-10", "marker": "today"}
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record_before) + "\n")
        log_file.write(json.dumps(record_after) + "\n")

    records = monitor_stocks._load_records_for_date(log_file_path, date(2026, 7, 10))

    assert len(records) == 1
    assert records[0]["marker"] == "today"


def test_load_records_for_date_returns_empty_list_when_file_missing(tmp_path):
    missing_log_file_path = str(tmp_path / "does_not_exist.jsonl")

    records = monitor_stocks._load_records_for_date(missing_log_file_path, date(2026, 7, 10))

    assert records == []


def test_load_records_for_date_skips_valid_json_that_is_not_a_dict(tmp_path):
    log_file_path = str(tmp_path / "run_log_stocks.jsonl")
    valid_record = {"market_date_eastern": "2026-07-10", "marker": "today"}
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(json.dumps(None) + "\n")
        log_file.write(json.dumps(valid_record) + "\n")

    records = monitor_stocks._load_records_for_date(log_file_path, date(2026, 7, 10))

    assert len(records) == 1
    assert records[0]["marker"] == "today"


def test_format_daily_report_reports_no_records_when_empty():
    report = monitor_stocks._format_daily_report([], date(2026, 7, 10))

    assert "美股每日報告 (2026-07-10 美東交易日)" in report
    assert "當日無任何執行紀錄" in report


def test_format_daily_report_reports_market_closed():
    records = [{"market_date_eastern": "2026-07-11", "market_open": False, "symbols": {}}]

    report = monitor_stocks._format_daily_report(records, date(2026, 7, 11))

    assert "今日美股休市, 無交易" in report


def test_format_daily_report_lists_submitted_orders():
    records = [
        {
            "market_date_eastern": "2026-07-10",
            "market_open": True,
            "account_equity_usd": 10_000.0,
            "day_start_equity_usd": 10_000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {
                "VOO": {
                    "risk_decision": {"type": "OrderEvent"},
                    "execution_result": {
                        "type": "SubmittedEvent", "symbol": "VOO", "side": "BUY",
                        "quantity": 10.0, "order_id": "order-1", "limit_price": 550.25,
                    },
                    "current_share_balance": 0.0,
                    "signal": {"latest_close_price": 550.25},
                },
                "QQQ": {
                    "risk_decision": {"type": "NoActionNeeded"},
                    "execution_result": None,
                    "current_share_balance": 0.0,
                    "signal": {"latest_close_price": 480.0},
                },
            },
        },
    ]

    report = monitor_stocks._format_daily_report(records, date(2026, 7, 10))

    assert "VOO: 買入 10.0 股 @ 550.25 限價 開盤委託已送出 (order_id=order-1)" in report
    assert "今日無新委託送出" not in report


def test_format_daily_report_shows_equity_change_percentage():
    records = [
        {
            "market_date_eastern": "2026-07-10",
            "market_open": True,
            "account_equity_usd": 9_900.0,
            "day_start_equity_usd": 10_000.0,
            "stale_symbols": {},
            "circuit_breaker_triggered": False,
            "symbols": {},
        },
    ]

    report = monitor_stocks._format_daily_report(records, date(2026, 7, 10))

    assert "帳戶淨值從 10000.00 變化至 9900.00 USD (-1.00%)" in report


def test_main_loads_formats_and_sends_report_for_previous_eastern_trading_day(monkeypatch):
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
    monkeypatch.setattr(monitor_stocks, "_load_records_for_date", _fake_load_records_for_date)
    monkeypatch.setattr(monitor_stocks, "_format_daily_report", _fake_format_daily_report)
    monkeypatch.setattr(
        monitor_stocks.telegram_alerts, "send_alert", lambda message: sent_messages.append(message)
    )

    monitor_stocks.main()

    expected_target_date = (
        datetime.now(monitor_stocks.US_EASTERN_TIMEZONE) - timedelta(days=1)
    ).date()
    assert captured["target_date"] == expected_target_date
    assert captured["format_target_date"] == expected_target_date
    assert captured["records"] == [{"marker": "fake_record"}]
    assert sent_messages == ["格式化後的報告文字"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_monitor_stocks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'monitor_stocks'`

- [ ] **Step 3: Implement**

Create `04_paper_trading/monitor_stocks.py`:

```python
"""
Phase 3 紙上交易 (paper trading) 美股每日報告 (monitor): 讀取 run_log_stocks.jsonl 中前一個美東交易日
的執行紀錄, 彙總成每日報告透過 Telegram 發送. 由獨立 crontab 於次日美股開盤前觸發.
與加密貨幣版 monitor.py 的關鍵差異: 這裡顯示的是已送出的開盤委託(SubmittedEvent, 尚未確認成交),
不是已確認成交; 是否成交由今日實際持倉(來自查詢到的真實 Alpaca 倉位) 間接反映.
見設計文件 docs/superpowers/specs/2026-07-10-phase3-us-stocks-paper-trading-design.md
用法: python3 monitor_stocks.py
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)

import telegram_alerts  # noqa: E402

LOG_FILE_PATH = os.path.join(_paper_trading_directory, "logs", "run_log_stocks.jsonl")
US_EASTERN_TIMEZONE = ZoneInfo("America/New_York")
EXPECTED_RUNS_PER_DAY = 1  # 美股排程每個交易日只觸發一次(收盤後), 與加密貨幣的每 4 小時一次不同


def _load_records_for_date(log_file_path: str, target_date: date) -> list[dict]:
    """
    逐行讀 log_file_path(jsonl), 只保留 market_date_eastern 等於 target_date 的紀錄(以美東交易日
    為準, 不是 UTC 日曆天, 因收盤後執行時 UTC 已跨到隔天). 檔案不存在時回傳空列表; 個別行解析失敗或
    不是 dict 時略過該行並印出警告, 不中止整份報告
    """
    if not os.path.exists(log_file_path):
        return []
    matched_records = []
    target_date_string = target_date.isoformat()
    with open(log_file_path, "r", encoding="utf-8") as log_file:
        for line_number, line in enumerate(log_file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise TypeError("record 不是 dict")
                market_date_eastern = record["market_date_eastern"]
            except (json.JSONDecodeError, KeyError, TypeError) as parse_error:
                print(f"略過無法解析的第 {line_number} 行: {parse_error}", file=sys.stderr)
                continue
            if market_date_eastern == target_date_string:
                matched_records.append(record)
    return matched_records


def _format_daily_report(records: list[dict], target_date: date) -> str:
    """把 _load_records_for_date 過濾出的當日 records 組成人類可讀的每日報告文字"""
    header_line = f"美股每日報告 ({target_date.isoformat()} 美東交易日)"
    if not records:
        return f"{header_line}\n當日無任何執行紀錄"

    latest_record = records[-1]
    if not latest_record.get("market_open", True):
        return f"{header_line}\n今日美股休市, 無交易"

    submission_lines = []
    for record in records:
        for symbol, symbol_record in record["symbols"].items():
            execution_result = symbol_record.get("execution_result")
            if execution_result is not None and execution_result["type"] == "SubmittedEvent":
                side_label = "買入" if execution_result["side"] == "BUY" else "賣出"
                price_label = (
                    f"@ {execution_result['limit_price']} 限價"
                    if execution_result.get("limit_price") is not None
                    else "市價"
                )
                submission_lines.append(
                    f"{symbol}: {side_label} {execution_result['quantity']} 股 {price_label} "
                    f"開盤委託已送出 (order_id={execution_result['order_id']})"
                )
    submission_section = "\n".join(submission_lines) if submission_lines else "今日無新委託送出"

    rejection_count = sum(
        1
        for record in records
        for symbol_record in record["symbols"].values()
        if symbol_record["risk_decision"]["type"] == "RejectionEvent"
    )
    stats_line = f"今日排程執行 {len(records)} / 預期 {EXPECTED_RUNS_PER_DAY} 次, 風控拒絕 {rejection_count} 次"

    day_start_equity = latest_record["day_start_equity_usd"]
    day_end_equity = latest_record["account_equity_usd"]
    equity_change_percentage = (day_end_equity - day_start_equity) / day_start_equity * 100
    equity_line = (
        f"帳戶淨值從 {day_start_equity:.2f} 變化至 {day_end_equity:.2f} USD "
        f"({equity_change_percentage:+.2f}%)"
    )

    position_lines = []
    for symbol, symbol_record in latest_record["symbols"].items():
        if "current_share_balance" not in symbol_record:
            continue
        balance = symbol_record["current_share_balance"]
        if balance != 0:
            latest_close_price = symbol_record["signal"]["latest_close_price"]
            position_lines.append(f"{symbol}: {balance} 股 (約 {balance * latest_close_price:.2f} USD)")
    position_section = "\n".join(position_lines) if position_lines else "目前無持倉"

    staleness_trigger_count = sum(1 for record in records if record["stale_symbols"])
    circuit_breaker_trigger_count = sum(1 for record in records if record["circuit_breaker_triggered"])
    health_line = (
        f"系統健康: 數據異常保護觸發 {staleness_trigger_count} 次, "
        f"每日熔斷觸發 {circuit_breaker_trigger_count} 次"
    )

    return "\n".join(
        [
            header_line, "", submission_section, "", stats_line, equity_line,
            "", "持倉:", position_section, "", health_line,
        ]
    )


def main() -> None:
    target_date = (datetime.now(US_EASTERN_TIMEZONE) - timedelta(days=1)).date()
    records = _load_records_for_date(LOG_FILE_PATH, target_date)
    report = _format_daily_report(records, target_date)
    telegram_alerts.send_alert(report)
    print(f"美股每日報告已發送 ({target_date.isoformat()}), 涵蓋 {len(records)} 筆執行紀錄")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_monitor_stocks.py -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite to confirm no regression**

Run: `pytest tests/ -v`
Expected: all tests PASS (crypto + stocks).

- [ ] **Step 6: Commit**

```bash
git add 04_paper_trading/monitor_stocks.py tests/test_monitor_stocks.py
git commit -m "feat: add monitor_stocks daily report for US-stocks paper trading"
```

---

### Task 9: Wiring, manual verification, and ROADMAP updates

This task has no new automated tests — it wires the already-tested code into the real environment and requires touching production scheduling (crontab) and a live paper-trading account, so it needs explicit human confirmation before any state-changing step, per this repo's global "confirm before side-effect commands" convention. Do not run the crontab-modifying step without the user's explicit go-ahead in the moment.

**Files:**
- Modify: `project_manage/ROADMAP.md` (check off completed items)
- Modify: `docs/superpowers/specs/2026-07-10-phase3-us-stocks-paper-trading-design.md` (append verification log, same convention as the Slice 2 spec's "實作後記錄" section)
- System: crontab (two new lines, added only with explicit user confirmation)

- [ ] **Step 1: Confirm the Alpaca paper account balance**

Ask the user to confirm (or confirm yourself if you have dashboard access) that the Alpaca Paper Trading account balance has been reset to **10,000 USD** via Alpaca's Reset Account feature, per the spec's "前置設置事項" section. This is a manual dashboard action, not a code change — do not proceed to Step 3 (real order submission) until this is confirmed, otherwise position sizing will be computed off the wrong equity base and the notional-cap risk check will reject almost every trade.

- [ ] **Step 2: Run the full test suite one more time**

Run: `pytest tests/ -v`
Expected: all tests PASS (crypto + US-stocks, no regressions from Tasks 1–8).

- [ ] **Step 3: Manual verification against the real Alpaca sandbox**

From `04_paper_trading/`, run:

```bash
python3 run_once_stocks.py
```

Two scenarios must each be observed at least once and written up (mirroring the Slice 2 spec's "實作後記錄" section — see `docs/superpowers/specs/2026-07-06-phase3-paper-trading-slice2-risk-rules-design.md` for the exact format to follow):

1. **On a weekend or US market holiday**: confirm the output shows `"market_open": false`, no Telegram alert was sent, and no entry was added to `logs/run_log_stocks.jsonl` beyond the no-op record itself.
2. **On a real US trading day, after actual NYSE close**: confirm `get_account()` / `get_positions()` return real data, at least one of VOO/QQQ produces a `SignalEvent`, and the resulting decision (`NoActionNeeded`, `RejectionEvent`, or an order submission producing a `SubmittedEvent`) is recorded correctly in `logs/run_log_stocks.jsonl`. If an order was submitted, check back after the next US market open (via the Alpaca dashboard or `get_positions()`) to confirm whether it filled or was auto-cancelled, and note which happened.

Record exactly what was and wasn't exercised — if, like the crypto Slice 2 verification, the signal happens to be flat (no order triggered), say so plainly rather than implying the order-submission path was tested. Append this write-up as a new section at the end of `docs/superpowers/specs/2026-07-10-phase3-us-stocks-paper-trading-design.md`, titled `## 實作後記錄: 執行紀錄(<date>)`.

- [ ] **Step 4: Wire up crontab — requires explicit user confirmation first**

Show the user these two lines and get explicit confirmation before applying them (do not pipe them into `crontab` non-interactively without that confirmation — this changes what runs unattended against a real, if paper, brokerage account going forward):

```
CRON_TZ=America/New_York
35 16 * * 1-5 cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 scheduler_stocks.py >> logs/cron.log 2>&1
0 8 * * 1-5 cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading && /usr/bin/python3 monitor_stocks.py >> logs/cron.log 2>&1
```

If the user confirms, apply with `crontab -e` (interactive) or by reading the current crontab with `crontab -l`, appending these lines, and reinstalling with `crontab -`. After applying, run `crontab -l` to show the user the final result. If `CRON_TZ` turns out to be unsupported by this system's cron (verify: after adding, check `grep CRON /var/log/syslog` or equivalent after the next scheduled tick, or consult `man 5 crontab` for this distribution), fall back to UTC-equivalent fixed times and note in the spec doc that DST transitions will need a manual twice-yearly adjustment (already documented as a known limitation in the spec's "排程 (crontab)" section).

- [ ] **Step 5: Update ROADMAP.md**

In `project_manage/ROADMAP.md`, find the line:

```
- [ ] `scheduler.py`: 美股每個交易日一次(美東 16:30 收盤後計算信號, 次日開盤前 30 分鐘掛限價單)
```

Replace it with:

```
- [x] `scheduler_stocks.py`: 美股每個交易日一次(美東收盤後計算信號並直接送開盤限價/市價委託, 由交易所在次日開盤拍賣時撮合, 不自建開盤前掛單流程, 見 `docs/superpowers/specs/2026-07-10-phase3-us-stocks-paper-trading-design.md`)
```

Only make this edit after Step 3's manual verification has actually been completed and written up — do not check this box based on the automated tests alone (per this project's convention of not calling engineering work "done" before it's been exercised against the real sandbox at least once).

- [ ] **Step 6: Commit**

```bash
git add project_manage/ROADMAP.md docs/superpowers/specs/2026-07-10-phase3-us-stocks-paper-trading-design.md
git commit -m "docs: record US-stocks paper trading verification and check off ROADMAP item"
```

If Step 4's crontab change was applied, mention in the commit body or a follow-up message that the crontab was modified (crontab itself isn't part of the git repo, so it won't show up in `git status` — call it out explicitly so it isn't a silent, undocumented change).

---

## Self-Review Notes

**Spec coverage:** VOO/QQQ symbols (Task 6 `SYMBOLS`), separate log/state files (Task 6 `LOG_FILE_PATH`/`DAILY_STATE_FILE_PATH`), Alpaca client with account/positions/calendar/LOO/MOO (Task 3), stock-specific data/execution agents (Tasks 4–5), `SYMBOL_MARKET_TYPES` + `limit_price` population (Task 2), `SubmittedEvent` (Task 1), calendar no-op gating (Task 6), next-day natural reconciliation (Task 6's `get_positions()` call + design note, no extra code needed), monitor differentiating submitted-vs-filled (Task 8), $10,000 pre-flight balance reset (Task 9 Step 1), crontab with `CRON_TZ` (Task 9 Step 4), ROADMAP update (Task 9 Step 5) — all covered.

**Placeholder scan:** no TBD/TODO; every step has complete, runnable code; no "similar to Task N" references.

**Type consistency:** `OrderEvent.limit_price` (Task 1) → read in `risk_agent.review_portfolio` (Task 2) → read in `stock_execution_agent.execute` (Task 5) → passed through to `SubmittedEvent.limit_price` (Task 5) → read in `monitor_stocks._format_daily_report` (Task 8) — same field name throughout. `market_date_eastern` key name consistent between `run_once_stocks.py` (Task 6, written) and `monitor_stocks.py` (Task 8, read). `current_share_balance` key name consistent between Task 6 (written) and Task 8 (read). `account_equity_usd` / `day_start_equity_usd` consistent between Task 6 and Task 8.
