# Phase 3 紙上交易 (paper trading) Slice 2 Implementation Plan : 風控硬性規則與雙標的擴展

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Slice 1 的 4-agent pipeline 上, 新增 ROADMAP 列出的 5 條風控 (risk control) 硬性規則, 並把交易標的由 BTC/USDT 單一標的擴展為 BTC/USDT + ETH/USDT 雙標的, 讓「最大同時持倉數」與「相關性限制」兩條跨標的規則有真實的第二標的可以比較, 同時整合真實 Telegram 警報.

**Architecture:** `run_once.py` 由 Slice 1 的單標的循序呼叫改為兩階段編排 : 收集階段對 `["BTCUSDT", "ETHUSDT"]` 各自跑 `data_agent` + `signal_agent`(含逐標的數據異常檢查) , 再交給單一 `risk_agent.review_portfolio(...)` 呼叫一次對整批標的做出決策(全域每日熔斷 → 逐標的數據異常 → 逐標的目標倉位比對 → 開倉方向四項檢查) , 最後對核准的訂單執行. 5 條新規則各自是獨立的純函式, 由 `review_portfolio` 依固定順序組合呼叫.

**Tech Stack:** Python 3.11+, pandas, numpy, requests, python-dotenv(皆已在 `requirements.txt`, 不新增依賴) . Telegram 警報用標準庫 `requests` 直接呼叫 Bot API, 不引入 `python-telegram-bot`.

**參照文件:** `docs/superpowers/specs/2026-07-06-phase3-paper-trading-slice2-risk-rules-design.md`(設計規格, 已核准) .

## Global Constraints

- 不新增 `requirements.txt` 依賴; Telegram 警報用既有的 `requests` 直接呼叫 Bot API 的 `sendMessage` 端點.
- 變數名, 函式名, DataFrame 欄位名一律用完整描述性英文, 不縮寫(CLAUDE.md Naming) .
- 中文文字一律用英文標點, 且每個標點後面留一個空格, 縮寫在同一檔案內首次出現需標註全稱(CLAUDE.md Writing) .
- 訊號 / 指標邏輯一律向量化, 不用 `for` / `if-else`; 執行層 I/O 控制流程與純風控決策邏輯(例如 `review_portfolio` 逐標的迴圈) 允許用 `for` 迴圈, 因為這是決策編排, 不是訊號/指標計算, 與 Slice 1 的既有慣例一致.
- 所有新的風控規則函式("check_" 開頭) 皆為純函式(不含 I/O) , 回傳 `True` 代表「通過, 可以繼續」, `False` 代表「應拒絕」; 依 TDD(test-driven development, 測試驅動開發) 撰寫, 且**必須涵蓋邊界值本身**(剛好等於門檻) , 不只測試明顯高於/低於, 修正 Slice 1 事後記錄的已知缺口.
- `review_portfolio` 依 `SYMBOL_MARKET_TYPES` 常數定義的固定標的順序處理(而非呼叫端傳入字典的隨意順序) , 讓「最大同時持倉數」與「相關性限制」的結果具決定性, 不隨呼叫端字典建構順序而變.
- `daily_risk_state.py` 的檔案 I/O(本機讀寫, 非網路請求) 依 TDD 撰寫並自動化測試(用 `tmp_path` fixture) ; `telegram_alerts.py` 對真實 Telegram API 的呼叫, 依 Slice 1 的既有慣例(`execution_agent.py` 對 `binance_testnet_client` 的作法) , 用 `monkeypatch` 取代 `requests.post` 寫自動化測試, 不打真實網路請求; 完整 `run_once.py` pipeline 與真實 Telegram 發送兩者皆在本切片收尾時各手動驗證一次.
- 每個任務完成後執行 `git add` + `git commit` + `git push` 到目前分支(CLAUDE.md Git, 不需再次確認) .
- 本切片範圍 : 5 條風控硬性規則 + BTC/USDT 與 ETH/USDT 雙標的 + 真實 Telegram 警報. 不做 Alpaca 美股 / `scheduler.py` 排程自動化 / `monitor.py` 每日彙總報告 / WebSocket(見設計文件排除範圍) .

## File Structure

新增檔案 :
- `04_paper_trading/daily_risk_state.py` — 每日風控狀態的讀寫與重置判斷
- `04_paper_trading/telegram_alerts.py` — Telegram 警報發送
- `tests/test_daily_risk_state.py`
- `tests/test_telegram_alerts.py`

修改檔案 :
- `04_paper_trading/agents/risk_agent.py` — 新增 5 條規則的純函式 + `SYMBOL_MARKET_TYPES` 常數; 移除 `review()`, 新增 `review_portfolio()`
- `tests/test_paper_trading_risk_agent.py` — 新增 5 條規則的測試 + `review_portfolio` 的整合測試; 移除針對舊 `review()` 的測試
- `04_paper_trading/run_once.py` — 由單標的循序呼叫改為兩階段多標的編排
- `docs/superpowers/specs/2026-07-06-phase3-paper-trading-slice2-risk-rules-design.md` — 收尾時附上手動驗證的執行紀錄(比照 Slice 1 慣例)

不修改 : `04_paper_trading/events.py`, `04_paper_trading/binance_testnet_client.py`, `04_paper_trading/agents/data_agent.py`, `04_paper_trading/agents/signal_agent.py`, `04_paper_trading/agents/execution_agent.py`, `.env.example`(已有 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 佔位, 見 Task 7) .

---

### Task 1: `daily_risk_state.py` — 每日風控狀態讀寫

**Files:**
- Create: `04_paper_trading/daily_risk_state.py`
- Test: `tests/test_daily_risk_state.py`

**Interfaces:**
- Produces: `should_reset_for_new_day(stored_utc_date: str | None, current_utc_date: str) -> bool`, `load_daily_state(file_path: str) -> dict`, `save_daily_state(file_path: str, state: dict) -> None` — Task 6(`run_once.py`) 會呼叫這三個函式.

- [ ] **Step 1: 寫失敗測試**

Create `tests/test_daily_risk_state.py`:

```python
"""daily_risk_state 的單元測試 — 純函式的重置判斷邏輯, 以及本機檔案 I/O 的讀寫往返"""
import os

import daily_risk_state


def test_should_reset_for_new_day_when_date_differs():
    assert daily_risk_state.should_reset_for_new_day("2026-07-05", "2026-07-06") is True


def test_should_reset_for_new_day_when_date_matches():
    assert daily_risk_state.should_reset_for_new_day("2026-07-06", "2026-07-06") is False


def test_should_reset_for_new_day_when_no_stored_date():
    assert daily_risk_state.should_reset_for_new_day(None, "2026-07-06") is True


def test_load_daily_state_returns_empty_dict_when_file_missing(tmp_path):
    missing_file_path = str(tmp_path / "does_not_exist.json")
    assert daily_risk_state.load_daily_state(missing_file_path) == {}


def test_load_daily_state_returns_empty_dict_when_file_corrupted(tmp_path):
    corrupted_file_path = tmp_path / "corrupted.json"
    corrupted_file_path.write_text("{not valid json", encoding="utf-8")
    assert daily_risk_state.load_daily_state(str(corrupted_file_path)) == {}


def test_save_and_load_daily_state_round_trip(tmp_path):
    state_file_path = str(tmp_path / "nested_directory" / "daily_risk_state.json")
    state = {"utc_date": "2026-07-06", "equity_at_day_start_usdt": 10_000.0}

    daily_risk_state.save_daily_state(state_file_path, state)
    loaded_state = daily_risk_state.load_daily_state(state_file_path)

    assert loaded_state == state
    assert os.path.exists(state_file_path)
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_daily_risk_state.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'daily_risk_state'`

- [ ] **Step 3: 建立 `04_paper_trading/daily_risk_state.py`**

```python
"""
每日風控狀態 — 記錄「今天(UTC) 開始時的帳戶淨值」, 供每日虧損熔斷(daily circuit breaker) 規則
計算「當日累計虧損」用. `run_once.py` 刻意保持無狀態(每次都查詢交易所真實狀態, 不信任本地記憶) ,
但交易所現貨帳戶沒有「今天損益」這種端點可查, 這份小型本地快取只補這一個交易所查不到的基準點,
本身不是真相來源 — 真相來源永遠是查詢到的當前淨值, 這份檔案只回答「要跟哪一個基準比」
"""
import json
import os


def should_reset_for_new_day(stored_utc_date, current_utc_date: str) -> bool:
    """比對儲存的 UTC 日期字串與現在的 UTC 日期字串, 不同(含尚無儲存值) 即需要重置每日基準"""
    return stored_utc_date != current_utc_date


def load_daily_state(file_path: str) -> dict:
    """
    讀取每日風控狀態檔; 檔案不存在或內容無法解析時, 回傳空字典(呼叫端會視為「尚無基準」, 直接重置) ,
    不因本地快取損壞而中止或阻擋交易 — 這份檔案是本地快取, 不是真相來源
    """
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as state_file:
            return json.load(state_file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_daily_state(file_path: str, state: dict) -> None:
    """把每日風控狀態寫入檔案, 目錄不存在時自動建立"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as state_file:
        json.dump(state, state_file)
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest tests/test_daily_risk_state.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add 04_paper_trading/daily_risk_state.py tests/test_daily_risk_state.py
git commit -m "feat: add daily_risk_state for circuit breaker baseline tracking"
git push
```

---

### Task 2: `telegram_alerts.py` — Telegram 警報發送

**Files:**
- Create: `04_paper_trading/telegram_alerts.py`
- Test: `tests/test_telegram_alerts.py`

**Interfaces:**
- Produces: `send_alert(message: str) -> None` — Task 6(`run_once.py`) 會在每日熔斷觸發與數據異常時呼叫.

- [ ] **Step 1: 寫失敗測試**

Create `tests/test_telegram_alerts.py`:

```python
"""telegram_alerts.send_alert 的單元測試 — monkeypatch 掉 requests.post, 不打真實網路請求"""
import telegram_alerts


class _FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def test_send_alert_succeeds_when_api_returns_200(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat-id")
    monkeypatch.setattr(
        telegram_alerts.requests, "post", lambda url, json, timeout: _FakeResponse(200)
    )

    telegram_alerts.send_alert("測試訊息")  # 不應拋出例外


def test_send_alert_does_not_raise_when_network_exception(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat-id")

    def _raise_network_error(url, json, timeout):
        raise telegram_alerts.requests.exceptions.ConnectionError("模擬網路斷線")

    monkeypatch.setattr(telegram_alerts.requests, "post", _raise_network_error)

    telegram_alerts.send_alert("測試訊息")  # 不應拋出例外


def test_send_alert_does_not_raise_when_credentials_missing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    telegram_alerts.send_alert("測試訊息")  # 不應拋出例外, 只印出提示


def test_send_alert_does_not_raise_when_api_returns_non_200(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat-id")
    monkeypatch.setattr(
        telegram_alerts.requests,
        "post",
        lambda url, json, timeout: _FakeResponse(400, "Bad Request: chat not found"),
    )

    telegram_alerts.send_alert("測試訊息")  # 不應拋出例外
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_telegram_alerts.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'telegram_alerts'`

- [ ] **Step 3: 建立 `04_paper_trading/telegram_alerts.py`**

```python
"""
Telegram 警報 — 對 Telegram Bot API 發送文字訊息, 用於每日熔斷與數據異常保護規則觸發時通知使用者
與 binance_testnet_client.py 相同手法, 從 .env 讀取憑證; 發送失敗只記錄, 不往外拋例外 —
警報是否送達不該推翻或中止一個已經正確做出的風控決策
"""
import os

import requests
from dotenv import load_dotenv

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
_repository_root = os.path.dirname(_paper_trading_directory)
load_dotenv(os.path.join(_repository_root, ".env"))

TELEGRAM_API_BASE_URL = "https://api.telegram.org"
REQUEST_TIMEOUT_SECONDS = 10


def send_alert(message: str) -> None:
    """
    發送一則文字訊息到設定好的 Telegram 聊天; 缺少憑證, 網路例外, 或非 200 回應皆只印出清楚的
    失敗訊息並返回, 不拋出例外(避免警報通道故障連帶讓風控決策已經完成的這次執行以例外中止)
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print(f"Telegram 警報未發送(缺少憑證) , 原始訊息: {message}")
        return

    url = f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/sendMessage"
    try:
        response = requests.post(
            url, json={"chat_id": chat_id, "text": message}, timeout=REQUEST_TIMEOUT_SECONDS
        )
        if response.status_code != 200:
            print(f"Telegram 警報發送失敗, HTTP {response.status_code}: {response.text}")
    except requests.exceptions.RequestException as network_error:
        print(f"Telegram 警報發送時發生網路例外: {network_error}, 原始訊息: {message}")
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest tests/test_telegram_alerts.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add 04_paper_trading/telegram_alerts.py tests/test_telegram_alerts.py
git commit -m "feat: add telegram_alerts for real-time risk rule notifications"
git push
```

---

### Task 3: `risk_agent.py` — 三條門檻型風控規則

**Files:**
- Modify: `04_paper_trading/agents/risk_agent.py`(在現有 `compute_buy_quantity` 函式之後, `review` 函式之前插入)
- Modify: `tests/test_paper_trading_risk_agent.py`

**Interfaces:**
- Produces: `check_max_loss_per_trade(order_quantity: float, average_true_range: float, atr_stop_multiplier: float, account_equity_usdt: float, max_loss_per_trade_fraction: float = 0.015) -> bool`, `check_daily_circuit_breaker(account_equity_usdt: float, day_start_equity_usdt: float, max_daily_loss_fraction: float = 0.04) -> bool`, `check_max_concurrent_positions(current_position_count: int, market_type: str, max_positions_by_market: dict) -> bool` — Task 5(`review_portfolio`) 與 Task 6(`run_once.py`) 會呼叫這些函式.

- [ ] **Step 1: 在 `tests/test_paper_trading_risk_agent.py` 新增失敗測試**

在既有的 `test_determine_current_position_long_when_above_dust_threshold` 之後(第 34 行之後) 插入 :

```python
def test_determine_current_position_exactly_at_dust_threshold_is_long():
    assert risk_agent.determine_current_position(0.0002, 50_000.0) == 1  # 市值剛好 10 USDT, 達門檻視為多單


def test_check_max_loss_per_trade_passes_within_cap():
    assert risk_agent.check_max_loss_per_trade(
        order_quantity=0.03,
        average_true_range=1_000.0,
        atr_stop_multiplier=2.0,
        account_equity_usdt=10_000.0,
        max_loss_per_trade_fraction=0.015,
    ) is True  # 潛在虧損 = 0.03 * 2 * 1000 = 60, 上限 = 10000 * 0.015 = 150


def test_check_max_loss_per_trade_passes_at_exact_boundary():
    assert risk_agent.check_max_loss_per_trade(
        order_quantity=0.075,
        average_true_range=1_000.0,
        atr_stop_multiplier=2.0,
        account_equity_usdt=10_000.0,
        max_loss_per_trade_fraction=0.015,
    ) is True  # 潛在虧損 = 0.075 * 2 * 1000 = 150, 剛好等於上限 150


def test_check_max_loss_per_trade_rejects_when_exceeding_cap():
    assert risk_agent.check_max_loss_per_trade(
        order_quantity=0.1,
        average_true_range=1_000.0,
        atr_stop_multiplier=2.0,
        account_equity_usdt=10_000.0,
        max_loss_per_trade_fraction=0.015,
    ) is False  # 潛在虧損 = 0.1 * 2 * 1000 = 200, 超過上限 150


def test_check_daily_circuit_breaker_passes_when_no_loss():
    assert risk_agent.check_daily_circuit_breaker(10_000.0, 10_000.0, 0.04) is True


def test_check_daily_circuit_breaker_passes_at_exact_boundary():
    assert risk_agent.check_daily_circuit_breaker(9_600.0, 10_000.0, 0.04) is True  # 虧損剛好 4%


def test_check_daily_circuit_breaker_rejects_when_exceeding_threshold():
    assert risk_agent.check_daily_circuit_breaker(9_500.0, 10_000.0, 0.04) is False  # 虧損 5%


def test_check_max_concurrent_positions_passes_below_cap():
    assert risk_agent.check_max_concurrent_positions(1, "crypto", {"crypto": 3, "stocks": 5}) is True


def test_check_max_concurrent_positions_passes_just_below_cap():
    assert risk_agent.check_max_concurrent_positions(2, "crypto", {"crypto": 3, "stocks": 5}) is True


def test_check_max_concurrent_positions_rejects_at_cap():
    assert risk_agent.check_max_concurrent_positions(3, "crypto", {"crypto": 3, "stocks": 5}) is False
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_paper_trading_risk_agent.py -v`
Expected: FAIL, `AttributeError: module 'risk_agent' has no attribute 'check_max_loss_per_trade'`(其餘新函式同理)

- [ ] **Step 3: 在 `04_paper_trading/agents/risk_agent.py` 的 `compute_buy_quantity` 之後, `review` 之前插入**

```python
def check_max_loss_per_trade(
    order_quantity: float,
    average_true_range: float,
    atr_stop_multiplier: float,
    account_equity_usdt: float,
    max_loss_per_trade_fraction: float = 0.015,
) -> bool:
    """
    估算這筆開倉若觸及停損會虧損多少(數量 × 停損距離) , 回傳 True 代表未超過帳戶淨值上限
    這與既有的名目金額上限是不同維度的雙層防呆(defense-in-depth) : 一個限制潛在虧損,
    一個限制部位金額本身; 在凍結的 exp_002 風險比例(1%) 下, 這條規則正常情況下不會觸發,
    只在風險比例設定被改動或計算異常時才會攔下, 與既有名目金額上限的防呆精神一致
    """
    potential_loss_usdt = order_quantity * atr_stop_multiplier * average_true_range
    return potential_loss_usdt <= account_equity_usdt * max_loss_per_trade_fraction


def check_daily_circuit_breaker(
    account_equity_usdt: float,
    day_start_equity_usdt: float,
    max_daily_loss_fraction: float = 0.04,
) -> bool:
    """回傳 True 代表尚未觸發每日熔斷; 當日開始淨值為 0 或負值時視為無法判斷, 保守放行不誤擋"""
    if day_start_equity_usdt <= 0:
        return True
    daily_loss_fraction = (day_start_equity_usdt - account_equity_usdt) / day_start_equity_usdt
    return daily_loss_fraction <= max_daily_loss_fraction


def check_max_concurrent_positions(
    current_position_count: int, market_type: str, max_positions_by_market: dict
) -> bool:
    """回傳 True 代表該類別(加密貨幣或美股) 尚未達最大同時持倉數上限"""
    return current_position_count < max_positions_by_market[market_type]
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest tests/test_paper_trading_risk_agent.py -v`
Expected: 16 passed(既有 6 個 + 本任務新增 10 個; 既有 4 個 review 相關測試留待 Task 5 替換, 此處不受影響仍會通過)

- [ ] **Step 5: Commit**

```bash
git add 04_paper_trading/agents/risk_agent.py tests/test_paper_trading_risk_agent.py
git commit -m "feat: add max-loss-per-trade, daily-circuit-breaker, max-concurrent-positions risk rules"
git push
```

---

### Task 4: `risk_agent.py` — 相關性限制與數據異常保護

**Files:**
- Modify: `04_paper_trading/agents/risk_agent.py`(在 Task 3 新增的函式之後插入; 檔案頂部新增 `from datetime import datetime, timedelta` 匯入)
- Modify: `tests/test_paper_trading_risk_agent.py`(檔案頂部新增 `import pandas as pd` 與 `from datetime import timedelta` 匯入)

**Interfaces:**
- Consumes: `pandas`(既有專案依賴) .
- Produces: `check_correlation_limit(candidate_close_price_series: pd.Series, existing_position_close_price_series: dict, max_correlation: float = 0.8) -> bool`, `check_data_staleness(last_candle_open_time: datetime, current_time: datetime, bar_interval: timedelta = timedelta(days=1), staleness_multiplier: float = 1.5) -> bool` — Task 5 會呼叫 `check_correlation_limit`; Task 6(`run_once.py`) 會在收集階段直接呼叫 `check_data_staleness`.

- [ ] **Step 1: 在 `tests/test_paper_trading_risk_agent.py` 頂部新增匯入, 並新增失敗測試**

把檔案開頭的 :

```python
from datetime import datetime, timezone

import pytest
```

改成 :

```python
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
```

在 Task 3 新增的測試之後追加 :

```python
def test_check_correlation_limit_passes_when_no_existing_positions():
    candidate_close_prices = pd.Series([100.0, 101.0, 102.0])
    assert risk_agent.check_correlation_limit(candidate_close_prices, {}) is True


def test_check_correlation_limit_passes_when_returns_are_negatively_correlated():
    # candidate 與 existing 每一步漲跌方向都相反, 相關係數應明顯為負, 遠低於 0.8 上限
    candidate_close_prices = pd.Series([100.0, 110.0, 100.0, 110.0, 100.0, 110.0])
    existing_close_prices = pd.Series([100.0, 90.0, 100.0, 90.0, 100.0, 90.0])
    assert risk_agent.check_correlation_limit(
        candidate_close_prices, {"ETHUSDT": existing_close_prices}, max_correlation=0.8
    ) is True


def test_check_correlation_limit_rejects_when_perfectly_correlated():
    candidate_close_prices = pd.Series([100.0, 102.0, 99.0, 105.0, 110.0])
    existing_close_prices = candidate_close_prices * 2.0  # 純比例縮放, 報酬率與 candidate 完全相同
    assert risk_agent.check_correlation_limit(
        candidate_close_prices, {"ETHUSDT": existing_close_prices}, max_correlation=0.8
    ) is False


def test_check_correlation_limit_rejects_when_insufficient_overlap():
    candidate_close_prices = pd.Series([100.0, 101.0])  # pct_change 後只剩 1 個數據點
    existing_close_prices = pd.Series([100.0, 101.0])
    assert risk_agent.check_correlation_limit(
        candidate_close_prices, {"ETHUSDT": existing_close_prices}, max_correlation=0.8
    ) is False


def test_check_data_staleness_passes_when_within_threshold():
    current_time = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    last_candle_open_time = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)  # 24 小時前開盤
    assert risk_agent.check_data_staleness(
        last_candle_open_time, current_time, timedelta(days=1), 1.5
    ) is True


def test_check_data_staleness_passes_at_exact_boundary():
    current_time = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    last_candle_open_time = datetime(2026, 7, 4, 0, 0, tzinfo=timezone.utc)
    # 約略收盤時間 = 開盤 + 1 天 = 2026-07-05 00:00, 距今 1.5 天, 剛好等於門檻
    assert risk_agent.check_data_staleness(
        last_candle_open_time, current_time, timedelta(days=1), 1.5
    ) is True


def test_check_data_staleness_rejects_when_beyond_threshold():
    current_time = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    last_candle_open_time = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)  # 3 天前開盤
    assert risk_agent.check_data_staleness(
        last_candle_open_time, current_time, timedelta(days=1), 1.5
    ) is False
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_paper_trading_risk_agent.py -v`
Expected: FAIL, `AttributeError: module 'risk_agent' has no attribute 'check_correlation_limit'`(`check_data_staleness` 同理)

- [ ] **Step 3: 在 `04_paper_trading/agents/risk_agent.py` 頂部新增匯入, 並在 Task 3 新增函式之後插入**

把檔案開頭的 :

```python
import os
import sys

import pandas as pd
```

改成 :

```python
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
```

在 `check_max_concurrent_positions` 之後追加 :

```python
def check_correlation_limit(
    candidate_close_price_series: pd.Series,
    existing_position_close_price_series: dict,
    max_correlation: float = 0.8,
) -> bool:
    """
    回傳 True 代表候選標的與所有現有持倉的日報酬率相關係數皆未超過上限, 可以開倉
    任一現有持倉缺少至少 2 個重疊報酬率數據點, 或相關係數算出 NaN(例如某段價格完全不變) ,
    視為無法確認風險, 直接回傳 False(風控規則寧可保守拒絕, 不因數據不足而放行)
    """
    if not existing_position_close_price_series:
        return True
    candidate_returns = candidate_close_price_series.pct_change().dropna()
    for existing_returns_series in existing_position_close_price_series.values():
        existing_returns = existing_returns_series.pct_change().dropna()
        overlapping_length = min(len(candidate_returns), len(existing_returns))
        if overlapping_length < 2:
            return False
        aligned_candidate_returns = candidate_returns.iloc[-overlapping_length:].reset_index(
            drop=True
        )
        aligned_existing_returns = existing_returns.iloc[-overlapping_length:].reset_index(
            drop=True
        )
        correlation = aligned_candidate_returns.corr(aligned_existing_returns)
        if pd.isna(correlation) or correlation > max_correlation:
            return False
    return True


def check_data_staleness(
    last_candle_open_time: datetime,
    current_time: datetime,
    bar_interval: timedelta = timedelta(days=1),
    staleness_multiplier: float = 1.5,
) -> bool:
    """
    回傳 True 代表數據新鮮, 可以繼續產生信號; False 代表已過期, 應暫停該標的的信號生成
    以「最後一根 K 線的約略收盤時間(開盤時間 + 一個週期) 」到現在經過的時間,
    對比 K 線週期的 staleness_multiplier 倍門檻 — 用相對於週期的門檻, 而非固定分鐘數,
    因為 exp_002 策略以日線決策, 固定的短分鐘數門檻對日線沒有意義(見設計文件)
    """
    approximate_close_time = last_candle_open_time + bar_interval
    time_since_close = current_time - approximate_close_time
    return time_since_close <= bar_interval * staleness_multiplier
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest tests/test_paper_trading_risk_agent.py -v`
Expected: 23 passed(Task 3 完成後 16 個 + 本任務新增 7 個)

- [ ] **Step 5: Commit**

```bash
git add 04_paper_trading/agents/risk_agent.py tests/test_paper_trading_risk_agent.py
git commit -m "feat: add correlation-limit and data-staleness risk rules"
git push
```

---

### Task 5: `risk_agent.py` — `review_portfolio` 取代 `review`

**Files:**
- Modify: `04_paper_trading/agents/risk_agent.py`(刪除 `review` 函式, 新增 `SYMBOL_MARKET_TYPES` 常數與 `review_portfolio` 函式)
- Modify: `tests/test_paper_trading_risk_agent.py`(刪除針對舊 `review` 的 4 個測試, 新增 `review_portfolio` 的整合測試)

**Interfaces:**
- Consumes: Task 3 的 `check_max_loss_per_trade` / `check_daily_circuit_breaker` / `check_max_concurrent_positions`; Task 4 的 `check_correlation_limit`; 既有的 `determine_current_position` / `compute_buy_quantity`; `events.OrderEvent` / `RejectionEvent` / `SignalEvent`.
- Produces: `review_portfolio(signal_events: dict, stale_symbols: list, current_base_asset_balances: dict, account_equity_usdt: float, day_start_equity_usdt: float, close_price_histories: dict, engine_parameters: dict, risk_limits: dict) -> dict`, 模組常數 `SYMBOL_MARKET_TYPES: dict` — Task 6(`run_once.py`) 會呼叫 `review_portfolio`.
- Removes: `review(...)`(Slice 1 函式, Task 6 完成後不再被任何程式呼叫) .

- [ ] **Step 1: 刪除 `tests/test_paper_trading_risk_agent.py` 中針對舊 `review` 的 4 個測試, 新增 `review_portfolio` 的失敗測試**

刪除以下 4 個測試函式(`test_review_returns_none_when_target_matches_current`、`test_review_returns_sell_order_closing_full_position`、`test_review_returns_buy_order_within_risk_cap`、`test_review_rejects_buy_when_notional_exceeds_cap`) , 在檔案頂部 `ENGINE_PARAMETERS` 定義之後新增 :

```python
RISK_LIMITS = {
    "max_loss_per_trade_fraction": 0.015,
    "max_daily_loss_fraction": 0.04,
    "max_positions_by_market": {"crypto": 3, "stocks": 5},
    "max_correlation": 0.8,
}


def _make_close_price_series(values):
    return pd.Series(values, dtype=float)
```

並把 `_make_signal_event` 改成接受 `symbol` 參數(原本寫死 `"BTCUSDT"`) :

```python
def _make_signal_event(
    symbol="BTCUSDT",
    target_position=1,
    close_price: float = 50_000.0,
    average_true_range: float = 1_000.0,
):
    return SignalEvent(
        symbol=symbol,
        target_position=target_position,
        as_of_timestamp=datetime(2026, 7, 6, tzinfo=timezone.utc),
        latest_close_price=close_price,
        latest_average_true_range=average_true_range,
    )
```

在檔案末尾新增 :

```python
def test_review_portfolio_circuit_breaker_rejects_all_symbols():
    signal_events = {
        "BTCUSDT": _make_signal_event("BTCUSDT", target_position=1),
        "ETHUSDT": _make_signal_event("ETHUSDT", target_position=0),
    }

    decisions = risk_agent.review_portfolio(
        signal_events, [], {}, 9_500.0, 10_000.0, {}, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["BTCUSDT"], RejectionEvent)
    assert "熔斷" in decisions["BTCUSDT"].reason
    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "熔斷" in decisions["ETHUSDT"].reason


def test_review_portfolio_marks_stale_symbol_as_rejected_and_other_proceeds():
    signal_events = {"BTCUSDT": _make_signal_event("BTCUSDT", target_position=0)}

    decisions = risk_agent.review_portfolio(
        signal_events, ["ETHUSDT"], {}, 10_000.0, 10_000.0, {}, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "過期" in decisions["ETHUSDT"].reason
    assert decisions["BTCUSDT"] is None


def test_review_portfolio_returns_sell_order_closing_full_position():
    signal_events = {"BTCUSDT": _make_signal_event("BTCUSDT", target_position=0)}

    decisions = risk_agent.review_portfolio(
        signal_events, [], {"BTCUSDT": 0.05}, 10_000.0, 10_000.0, {}, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["BTCUSDT"], OrderEvent)
    assert decisions["BTCUSDT"].side == "SELL"
    assert decisions["BTCUSDT"].quantity == 0.05


def test_review_portfolio_approves_buy_when_alone_and_within_limits():
    signal_events = {
        "BTCUSDT": _make_signal_event(
            "BTCUSDT", target_position=1, close_price=50_000.0, average_true_range=1_000.0
        )
    }
    close_price_histories = {
        "BTCUSDT": _make_close_price_series([50_000.0 + index * 100 for index in range(30)])
    }

    decisions = risk_agent.review_portfolio(
        signal_events, [], {}, 10_000.0, 10_000.0, close_price_histories, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["BTCUSDT"], OrderEvent)
    assert decisions["BTCUSDT"].side == "BUY"
    assert decisions["BTCUSDT"].quantity == pytest.approx(0.05)


def test_review_portfolio_rejects_second_correlated_open_in_same_batch():
    btc_close_prices = _make_close_price_series([50_000.0 + index * 100 for index in range(30)])
    eth_close_prices = btc_close_prices * 2.0  # 純比例縮放, 相關係數必為 1.0
    signal_events = {
        "BTCUSDT": _make_signal_event(
            "BTCUSDT", target_position=1, close_price=50_000.0, average_true_range=1_000.0
        ),
        "ETHUSDT": _make_signal_event(
            "ETHUSDT", target_position=1, close_price=3_000.0, average_true_range=100.0
        ),
    }
    close_price_histories = {"BTCUSDT": btc_close_prices, "ETHUSDT": eth_close_prices}

    decisions = risk_agent.review_portfolio(
        signal_events, [], {}, 10_000.0, 10_000.0, close_price_histories, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["BTCUSDT"], OrderEvent)  # 依固定順序先處理, 當時尚無現有持倉可比較
    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "相關係數" in decisions["ETHUSDT"].reason


def test_review_portfolio_rejects_buy_when_max_loss_per_trade_exceeded():
    signal_events = {
        "BTCUSDT": _make_signal_event(
            "BTCUSDT", target_position=1, close_price=50_000.0, average_true_range=1_000.0
        )
    }
    close_price_histories = {
        "BTCUSDT": _make_close_price_series([50_000.0 + index * 100 for index in range(30)])
    }
    strict_risk_limits = dict(RISK_LIMITS, max_loss_per_trade_fraction=0.005)

    decisions = risk_agent.review_portfolio(
        signal_events, [], {}, 10_000.0, 10_000.0, close_price_histories, ENGINE_PARAMETERS, strict_risk_limits
    )

    assert isinstance(decisions["BTCUSDT"], RejectionEvent)
    assert "潛在虧損" in decisions["BTCUSDT"].reason


def test_review_portfolio_rejects_buy_when_max_concurrent_positions_reached():
    signal_events = {
        "BTCUSDT": _make_signal_event(
            "BTCUSDT", target_position=1, close_price=50_000.0, average_true_range=1_000.0
        ),
        "ETHUSDT": _make_signal_event(
            "ETHUSDT", target_position=1, close_price=3_000.0, average_true_range=100.0
        ),
    }
    current_base_asset_balances = {"BTCUSDT": 0.05}  # 市值 2500 USDT, 已是真實持倉
    close_price_histories = {
        "BTCUSDT": _make_close_price_series([50_000.0 + index * 100 for index in range(30)]),
        "ETHUSDT": _make_close_price_series([3_000.0 + index * 10 for index in range(30)]),
    }
    strict_risk_limits = dict(RISK_LIMITS, max_positions_by_market={"crypto": 1, "stocks": 5})

    decisions = risk_agent.review_portfolio(
        signal_events, [], current_base_asset_balances, 12_500.0, 12_500.0,
        close_price_histories, ENGINE_PARAMETERS, strict_risk_limits,
    )

    assert decisions["BTCUSDT"] is None  # 已是多單, 目標與當前相同
    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "持倉數" in decisions["ETHUSDT"].reason


def test_review_portfolio_rejects_buy_when_notional_exceeds_cap():
    signal_events = {
        "BTCUSDT": _make_signal_event(
            "BTCUSDT", target_position=1, close_price=50_000.0, average_true_range=1_000.0
        )
    }
    close_price_histories = {
        "BTCUSDT": _make_close_price_series([50_000.0 + index * 100 for index in range(30)])
    }
    small_cap_engine_parameters = dict(ENGINE_PARAMETERS, initial_capital=1_000.0)

    decisions = risk_agent.review_portfolio(
        signal_events, [], {}, 10_000.0, 10_000.0,
        close_price_histories, small_cap_engine_parameters, RISK_LIMITS,
    )

    assert isinstance(decisions["BTCUSDT"], RejectionEvent)
    assert "超過風控上限" in decisions["BTCUSDT"].reason
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_paper_trading_risk_agent.py -v`
Expected: FAIL, `AttributeError: module 'risk_agent' has no attribute 'review_portfolio'`

- [ ] **Step 3: 刪除 `04_paper_trading/agents/risk_agent.py` 的 `review` 函式, 改為以下內容**

刪除整個 `def review(...)` 函式(原設計文件版本, 位於檔案末尾) , 改成 :

```python
SYMBOL_MARKET_TYPES = {"BTCUSDT": "crypto", "ETHUSDT": "crypto"}


def review_portfolio(
    signal_events: dict,
    stale_symbols: list,
    current_base_asset_balances: dict,
    account_equity_usdt: float,
    day_start_equity_usdt: float,
    close_price_histories: dict,
    engine_parameters: dict,
    risk_limits: dict,
) -> dict:
    """
    對整批標的一次做出風控決策(取代 Slice 1 的單標的 review) , 依序套用 :
    全域每日熔斷(一次) → 逐標的數據異常 → 逐標的目標倉位比對 → 開倉方向四項檢查
    (單筆最大虧損, 最大同時持倉數, 相關性限制, 名目金額上限) . 依 SYMBOL_MARKET_TYPES 的固定
    標的順序處理, 讓「最大同時持倉數」與「相關性限制」的比較基準包含本次批次已核准的開倉,
    結果因此具決定性(取決於固定順序, 不取決於呼叫端字典的建構順序) , 見設計文件行為後果說明
    """
    decisions = {}
    ordered_symbols = [symbol for symbol in SYMBOL_MARKET_TYPES if symbol in signal_events]

    circuit_breaker_ok = check_daily_circuit_breaker(
        account_equity_usdt, day_start_equity_usdt, risk_limits["max_daily_loss_fraction"]
    )
    if not circuit_breaker_ok:
        for symbol in ordered_symbols + list(stale_symbols):
            decisions[symbol] = RejectionEvent(
                symbol=symbol, reason="每日虧損熔斷已觸發, 停止當日所有交易"
            )
        return decisions

    for symbol in stale_symbols:
        decisions[symbol] = RejectionEvent(symbol=symbol, reason="數據已過期, 暫停信號生成")

    open_long_symbols = [
        symbol
        for symbol in ordered_symbols
        if determine_current_position(
            current_base_asset_balances.get(symbol, 0.0),
            signal_events[symbol].latest_close_price,
        )
        == 1
    ]

    for symbol in ordered_symbols:
        signal_event = signal_events[symbol]
        current_position = determine_current_position(
            current_base_asset_balances.get(symbol, 0.0), signal_event.latest_close_price
        )
        if signal_event.target_position == current_position:
            decisions[symbol] = None
            continue

        if signal_event.target_position == 0:
            decisions[symbol] = OrderEvent(
                symbol=symbol, side="SELL", quantity=current_base_asset_balances.get(symbol, 0.0)
            )
            if symbol in open_long_symbols:
                open_long_symbols.remove(symbol)
            continue

        buy_quantity = compute_buy_quantity(
            account_equity_usdt,
            signal_event.latest_close_price,
            signal_event.latest_average_true_range,
            engine_parameters["risk_per_trade_percentage"],
            engine_parameters["atr_stop_multiplier"],
            engine_parameters["max_position_fraction"],
        )

        if not check_max_loss_per_trade(
            buy_quantity,
            signal_event.latest_average_true_range,
            engine_parameters["atr_stop_multiplier"],
            account_equity_usdt,
            risk_limits["max_loss_per_trade_fraction"],
        ):
            decisions[symbol] = RejectionEvent(symbol=symbol, reason="單筆潛在虧損超過風控上限")
            continue

        market_type = SYMBOL_MARKET_TYPES[symbol]
        positions_in_same_market_count = sum(
            1
            for other_symbol in open_long_symbols
            if SYMBOL_MARKET_TYPES.get(other_symbol) == market_type
        )
        if not check_max_concurrent_positions(
            positions_in_same_market_count, market_type, risk_limits["max_positions_by_market"]
        ):
            decisions[symbol] = RejectionEvent(
                symbol=symbol, reason=f"已達 {market_type} 類別最大同時持倉數上限"
            )
            continue

        existing_position_close_price_series = {
            other_symbol: close_price_histories[other_symbol]
            for other_symbol in open_long_symbols
            if other_symbol in close_price_histories
        }
        if not check_correlation_limit(
            close_price_histories[symbol],
            existing_position_close_price_series,
            risk_limits["max_correlation"],
        ):
            decisions[symbol] = RejectionEvent(symbol=symbol, reason="與現有持倉相關係數超過風控上限")
            continue

        notional_value_usdt = buy_quantity * signal_event.latest_close_price
        maximum_allowed_notional_usdt = (
            engine_parameters["initial_capital"] * engine_parameters["max_position_fraction"]
        )
        if notional_value_usdt > maximum_allowed_notional_usdt:
            decisions[symbol] = RejectionEvent(
                symbol=symbol,
                reason=(
                    f"買進名目金額 {notional_value_usdt:.2f} USDT 超過風控上限 "
                    f"{maximum_allowed_notional_usdt:.2f} USDT"
                ),
            )
            continue

        decisions[symbol] = OrderEvent(symbol=symbol, side="BUY", quantity=buy_quantity)
        open_long_symbols.append(symbol)

    return decisions
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest tests/test_paper_trading_risk_agent.py -v`
Expected: 27 passed(Task 4 完成後 23 個, 移除舊 review 的 4 個測試, 新增 review_portfolio 的 8 個測試 : 23 - 4 + 8 = 27)

- [ ] **Step 5: 執行完整測試套件確認沒有連帶破壞既有測試**

Run: `pytest tests/ -v`
Expected: 全部通過(確認沒有其他檔案還在呼叫已刪除的 `risk_agent.review`)

- [ ] **Step 6: Commit**

```bash
git add 04_paper_trading/agents/risk_agent.py tests/test_paper_trading_risk_agent.py
git commit -m "feat: replace single-symbol review with portfolio-wide review_portfolio"
git push
```

---

### Task 6: `run_once.py` — 兩階段多標的編排

**Files:**
- Modify: `04_paper_trading/run_once.py`(完整重寫)

**Interfaces:**
- Consumes: `data_agent.fetch_latest_candles`, `signal_agent.decide`, `signal_agent.FROZEN_ENGINE_PARAMETERS`(既有) ; `risk_agent.check_data_staleness`, `risk_agent.check_daily_circuit_breaker`, `risk_agent.review_portfolio`(Task 3-5) ; `daily_risk_state.load_daily_state` / `save_daily_state` / `should_reset_for_new_day`(Task 1) ; `telegram_alerts.send_alert`(Task 2) ; `execution_agent.execute`, `binance_testnet_client.get_account_balances` / `get_symbol_filters`(既有) .
- Produces: `run_once(symbols: list | None = None) -> dict`, 模組常數 `SYMBOLS`, `RISK_LIMITS`.

- [ ] **Step 1: 完整重寫 `04_paper_trading/run_once.py`**

```python
"""
Paper trading Slice 2 執行腳本 — 對 BTC/USDT 與 ETH/USDT 兩個標的一次執行
data → signal → risk → execution. 收集階段先跑完兩個標的的 data/signal(含逐標的數據異常檢查) ,
再交給 risk_agent 一次性做 portfolio 決策(最大同時持倉數與相關性限制等跨標的規則需要看到
所有標的才能判斷) , 最後執行核准的訂單. 任一標的的數據抓取失敗只影響該標的本身, 不中止其他標的
(與 Slice 1 單標的「整段失敗」不同, 見設計文件錯誤處理段落) . 手動觸發(非排程) , 每次執行都以
交易所真實帳戶狀態核對現有倉位, 重複執行安全(見設計文件冪等性討論)
用法: python run_once.py
"""
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)
sys.path.insert(0, os.path.join(_paper_trading_directory, "agents"))

import binance_testnet_client  # noqa: E402
import daily_risk_state  # noqa: E402
import data_agent  # noqa: E402
import execution_agent  # noqa: E402
import risk_agent  # noqa: E402
import signal_agent  # noqa: E402
import telegram_alerts  # noqa: E402
from events import OrderEvent  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
QUOTE_ASSET = "USDT"
BAR_INTERVAL = timedelta(days=1)
LOG_FILE_PATH = os.path.join(_paper_trading_directory, "logs", "run_log.jsonl")
DAILY_STATE_FILE_PATH = os.path.join(_paper_trading_directory, "logs", "daily_risk_state.json")

RISK_LIMITS = {
    "max_loss_per_trade_fraction": 0.015,
    "max_daily_loss_fraction": 0.04,
    "max_positions_by_market": {"crypto": 3, "stocks": 5},
    "max_correlation": 0.8,
}


def _base_asset_from_symbol(symbol: str) -> str:
    """從交易對代號取出基礎資產代號, 例如 "BTCUSDT" -> "BTC"(本專案交易對一律以 USDT 報價)"""
    return symbol.removesuffix(QUOTE_ASSET)


def _serialize_event(event) -> dict:
    """把 dataclass 事件轉成可寫入 JSON 的字典; 無事件(None, 代表無需動作) 轉成明確標記"""
    if event is None:
        return {"type": "NoActionNeeded"}
    serialized = asdict(event)
    serialized["type"] = type(event).__name__
    return serialized


def _append_log_record(record: dict) -> None:
    """把這次執行紀錄追加寫入 logs/run_log.jsonl(一行一筆 JSON, gitignore 排除) """
    os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)
    with open(LOG_FILE_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")


def run_once(symbols: list = None) -> dict:
    """
    跑一次完整 pipeline : 對每個標的收集 data/signal(含逐標的數據異常檢查) , 交給 risk_agent
    一次性做 portfolio 決策, 再執行核准的訂單.
    已知簡化: 若某標的本次抓取失敗且該標的目前有實際持倉, 其價值不計入 account_equity_usdt,
    這會讓淨值被低估, 使每日熔斷更容易觸發而非更難觸發, 是保守(安全) 的失敗方向, 而非危險方向
    """
    symbols = symbols if symbols is not None else SYMBOLS
    record = {"run_started_at": datetime.now(timezone.utc).isoformat(), "symbols": {}}

    daily_state = daily_risk_state.load_daily_state(DAILY_STATE_FILE_PATH)
    account_balances = binance_testnet_client.get_account_balances()

    signal_events = {}
    stale_symbols = []
    close_price_histories = {}
    current_base_asset_balances = {}
    fetch_failures = {}

    for symbol in symbols:
        try:
            ohlcv_dataframe = data_agent.fetch_latest_candles(symbol)
        except Exception as fetch_error:
            fetch_failures[symbol] = str(fetch_error)
            continue

        close_price_histories[symbol] = ohlcv_dataframe["close"]
        last_candle_open_time = (
            ohlcv_dataframe["open_time"].iloc[-1].to_pydatetime().replace(tzinfo=timezone.utc)
        )
        is_fresh = risk_agent.check_data_staleness(
            last_candle_open_time, datetime.now(timezone.utc), BAR_INTERVAL
        )
        if not is_fresh:
            stale_symbols.append(symbol)
            continue

        signal_event = signal_agent.decide(ohlcv_dataframe, symbol)
        signal_events[symbol] = signal_event
        current_base_asset_balances[symbol] = account_balances.get(
            _base_asset_from_symbol(symbol), 0.0
        )

    account_equity_usdt = account_balances.get(QUOTE_ASSET, 0.0) + sum(
        current_base_asset_balances[symbol] * signal_events[symbol].latest_close_price
        for symbol in signal_events
    )

    current_utc_date = datetime.now(timezone.utc).date().isoformat()
    if daily_risk_state.should_reset_for_new_day(daily_state.get("utc_date"), current_utc_date):
        daily_state = {"utc_date": current_utc_date, "equity_at_day_start_usdt": account_equity_usdt}
        daily_risk_state.save_daily_state(DAILY_STATE_FILE_PATH, daily_state)
    day_start_equity_usdt = daily_state["equity_at_day_start_usdt"]

    record["fetch_failures"] = fetch_failures
    record["stale_symbols"] = stale_symbols

    circuit_breaker_triggered = not risk_agent.check_daily_circuit_breaker(
        account_equity_usdt, day_start_equity_usdt, RISK_LIMITS["max_daily_loss_fraction"]
    )
    record["circuit_breaker_triggered"] = circuit_breaker_triggered
    if circuit_breaker_triggered:
        telegram_alerts.send_alert(
            f"每日虧損熔斷已觸發: 帳戶淨值從 {day_start_equity_usdt:.2f} USDT "
            f"降至 {account_equity_usdt:.2f} USDT, 停止今日所有交易"
        )
    if stale_symbols:
        telegram_alerts.send_alert(f"數據異常保護觸發, 暫停信號生成: {', '.join(stale_symbols)}")

    decisions = risk_agent.review_portfolio(
        signal_events,
        stale_symbols,
        current_base_asset_balances,
        account_equity_usdt,
        day_start_equity_usdt,
        close_price_histories,
        signal_agent.FROZEN_ENGINE_PARAMETERS,
        RISK_LIMITS,
    )

    for symbol, decision in decisions.items():
        symbol_record = {"risk_decision": _serialize_event(decision)}
        if isinstance(decision, OrderEvent):
            symbol_filters = binance_testnet_client.get_symbol_filters(symbol)
            execution_result = execution_agent.execute(decision, symbol_filters)
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

- [ ] **Step 2: 語法與匯入健檢**

Run: `cd 04_paper_trading && python3 -c "import run_once; print(run_once.SYMBOLS)" && cd ..`
Expected: `['BTCUSDT', 'ETHUSDT']`, 無例外(確認語法正確且所有匯入可解析; 尚未呼叫 `run_once()`, 不需要真實憑證)

- [ ] **Step 3: 執行完整測試套件確認沒有連帶破壞既有測試**

Run: `pytest tests/ -v`
Expected: 全部通過

- [ ] **Step 4: Commit**

```bash
git add 04_paper_trading/run_once.py
git commit -m "feat: restructure run_once.py to two-phase multi-symbol orchestration"
git push
```

---

### Task 7: 手動端到端驗證(真實 Binance Testnet + 真實 Telegram)

**Files:**
- Modify: `docs/superpowers/specs/2026-07-06-phase3-paper-trading-slice2-risk-rules-design.md`(附加執行紀錄, 比照 Slice 1 慣例)

這個任務沒有自動化測試步驟 : `telegram_alerts.send_alert` 對真實 API 的呼叫與完整 `run_once.py` pipeline 皆是刻意不自動化模擬的 I/O 邊界(見設計文件與 Global Constraints) , 改為手動執行驗證一次.

- [ ] **Step 1: 確認 `.env` 已填入真實憑證**

確認本機(不入 Git 的) `.env` 已有 `BINANCE_TESTNET_API_KEY` / `BINANCE_TESTNET_SECRET`(Slice 1 已用過) , 以及 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`(`.env.example` 已有對應佔位, 只需在本機 `.env` 填入真實值) .

- [ ] **Step 2: 手動驗證 Telegram 整合本身(獨立於完整 pipeline)**

Run:
```bash
cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading
python3 -c "import telegram_alerts; telegram_alerts.send_alert('Slice 2 手動驗證: Telegram 警報整合測試')"
```
Expected: 終端機無錯誤訊息輸出; 手機或 Telegram 客戶端的對應聊天視窗收到這則訊息. 若終端機印出「Telegram 警報發送失敗」或「未發送」, 先排查 `.env` 中的憑證是否正確, 再重試, 確認訊息真的送達後才進入下一步.

- [ ] **Step 3: 執行完整測試套件, 確認所有自動化測試通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && pytest tests/ -v`
Expected: 全部通過

- [ ] **Step 4: 手動執行一次完整 pipeline**

Run: `python3 04_paper_trading/run_once.py`
Expected: 印出 JSON 摘要, 含 `BTCUSDT` 與 `ETHUSDT` 兩個標的的 `risk_decision` 與 `execution_result`. 檢查 `04_paper_trading/logs/run_log.jsonl` 新增一行紀錄, `04_paper_trading/logs/daily_risk_state.json` 已建立且 `equity_at_day_start_usdt` 為合理數值.

- [ ] **Step 5: 立即再跑一次, 確認冪等性(idempotency)**

Run: `python3 04_paper_trading/run_once.py`
Expected: 兩個標的的 `risk_decision` 皆正確反映「目標倉位與剛才執行後的當前倉位相符」(多數情況下為 `NoActionNeeded`, 除非 exp_002 信號本身在兩次執行之間變化, 這在同一天內的日線策略下不會發生) , 沒有因為重複執行而產生非預期的重複下單.

- [ ] **Step 6: 把執行結果記錄進design文件, 並 Commit**

在 `docs/superpowers/specs/2026-07-06-phase3-paper-trading-slice2-risk-rules-design.md` 末尾新增一個章節, 比照 Slice 1 設計文件「實作後記錄」的格式, 記錄 :
- 兩次執行各自的 `risk_decision` 結果(BTC 與 ETH 各自是 `None` / `OrderEvent` / `RejectionEvent`)
- Telegram 測試訊息確認送達
- 若本次驗證剛好沒有觸發熔斷或相關性拒絕等規則, 明確寫下「本次驗證未觸發之規則」清單, 比照 Slice 1 「尚未被真實下單驗證過」的誠實記錄方式, 不假裝驗證了未觸發的路徑

```bash
git add docs/superpowers/specs/2026-07-06-phase3-paper-trading-slice2-risk-rules-design.md
git commit -m "docs: record Slice 2 manual verification execution log"
git push
```
