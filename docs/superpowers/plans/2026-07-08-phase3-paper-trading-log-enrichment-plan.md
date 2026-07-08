# Phase 3 紙上交易 (paper trading) 執行紀錄補齊 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `04_paper_trading/run_log.jsonl` 補齊成足以重建權益曲線、算 Sharpe/回撤、檢視手續費後績效、檢視風控參數鬆緊的完整紀錄, 不改變任何交易或風控的判斷結果.

**Architecture:** 5 個 tier 由淺到深: Tier 1/2/5 在 `run_once.py` 純新增已算好但沒記錄的欄位; Tier 4 在 `risk_agent.py` 抽出 4 個 pure helper 函式(計算數值)供既有 `check_*` 函式(判斷 bool)與 `review_portfolio`(記錄數值) 共用, 既有 `check_*` 的 bool 回傳合約完全不變; Tier 3 在 `execution_agent.py` 解析 Binance 成交回應既有的 `fills` 陣列取得手續費. `events.py` 的兩個 dataclass 新增欄位皆有預設值, 向下相容.

**Tech Stack:** Python 3, `pytest` + `monkeypatch`(既有測試慣例), `pandas`(相關係數計算), 無新依賴.

## Global Constraints

- 不新增任何風控規則, 不調整任何現有風控上限的數值.
- 不改變任何 `check_max_loss_per_trade`/`check_daily_circuit_breaker`/`check_correlation_limit`/`check_data_staleness` 的 bool 回傳合約, 這 4 個函式既有測試檔案裡的既有測試斷言內容不需要修改.
- `RejectionEvent`、`FillEvent` 的新欄位都要有預設值, 對既有呼叫端(不傳新欄位)完全向下相容.
- `review_portfolio` 的 `stale_symbols` 參數型別從 `list` 改成 `dict`(標的 → staleness 細節字典), 這是本次唯一一個會改變 `review_portfolio` 對外參數型別的地方.
- 補齊前已經寫入 `run_log.jsonl` 的舊格式紀錄不會被回填, 不需要處理相容性.
- `_compute_total_commission` 假設單一訂單所有 `fills` 的 `commissionAsset` 一致, 只取第一筆, 這是已知簡化.
- CLAUDE.md 標點規則: 中文文字一律只用英文標點 `. , ! ? : ; ()`, 不使用全形引號(如 `「」`)或破折號(如 `—`).
- CLAUDE.md 命名規則: 變數與欄位名一律用完整描述性名稱, 不縮寫.

---

## File Structure

- Modify: `04_paper_trading/events.py` : `RejectionEvent`、`FillEvent` 新增欄位
- Modify: `04_paper_trading/agents/risk_agent.py` : 新增 4 個 pure helper 函式, `check_*` 函式內部改用 helper, `review_portfolio` 記錄數值並改用 `stale_symbols: dict`
- Modify: `04_paper_trading/agents/execution_agent.py` : 新增 `_compute_total_commission`, `execute()` 填入 `FillEvent` 的手續費欄位
- Modify: `04_paper_trading/run_once.py` : `record` 新增帳戶淨值/參數快照/訊號上下文欄位, `stale_symbols` 改用 `dict`
- Modify: `tests/test_paper_trading_events.py`、`tests/test_paper_trading_risk_agent.py`、`tests/test_paper_trading_execution_agent.py`、`tests/test_paper_trading_run_once.py`

---

### Task 1: `events.py` 資料結構新增欄位

**Files:**
- Modify: `04_paper_trading/events.py`
- Test: `tests/test_paper_trading_events.py`

**Interfaces:**
- Produces: `RejectionEvent(symbol, reason, computed_value=None, limit_value=None)`, `FillEvent(symbol, side, quantity, average_price, order_id, commission=0.0, commission_asset="")` : 供 Task 2/3/4/5 建構這兩個事件時使用.

- [ ] **Step 1: 寫失敗測試, 確認 `RejectionEvent` 新欄位預設為 `None`, 且可被覆寫**

Append to `tests/test_paper_trading_events.py`:

```python
def test_rejection_event_defaults_computed_value_and_limit_value_to_none():
    rejection_event = RejectionEvent(symbol="BTCUSDT", reason="超過風控上限")
    assert rejection_event.computed_value is None
    assert rejection_event.limit_value is None


def test_rejection_event_holds_computed_value_and_limit_value_when_provided():
    rejection_event = RejectionEvent(
        symbol="BTCUSDT", reason="超過風控上限", computed_value=0.85, limit_value=0.8
    )
    assert rejection_event.computed_value == 0.85
    assert rejection_event.limit_value == 0.8
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_events.py -v`
Expected: FAIL : `TypeError: RejectionEvent.__init__() got an unexpected keyword argument 'computed_value'`

- [ ] **Step 3: 在 `RejectionEvent` 新增欄位**

In `04_paper_trading/events.py`, replace:

```python
@dataclass
class RejectionEvent:
    """risk_agent 認為該交易, 但被風控規則擋下"""

    symbol: str
    reason: str
```

with:

```python
@dataclass
class RejectionEvent:
    """risk_agent 認為該交易, 但被風控規則擋下"""

    symbol: str
    reason: str
    computed_value: float | None = None  # 觸發拒絕當下的實際計算值, 與 reason 描述的是同一種單位
    limit_value: float | None = None  # 對應的風控上限值, 與 computed_value 同單位
```

- [ ] **Step 4: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_events.py -v`
Expected: PASS

- [ ] **Step 5: 寫失敗測試, 確認 `FillEvent` 新欄位預設值與覆寫行為**

Append to `tests/test_paper_trading_events.py`:

```python
def test_fill_event_defaults_commission_to_zero():
    fill_event = FillEvent(
        symbol="BTCUSDT", side="BUY", quantity=0.01, average_price=50000.0, order_id="123"
    )
    assert fill_event.commission == 0.0
    assert fill_event.commission_asset == ""


def test_fill_event_holds_commission_when_provided():
    fill_event = FillEvent(
        symbol="BTCUSDT", side="BUY", quantity=0.01, average_price=50000.0, order_id="123",
        commission=1.25, commission_asset="USDT",
    )
    assert fill_event.commission == 1.25
    assert fill_event.commission_asset == "USDT"
```

- [ ] **Step 6: 執行測試確認失敗**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_events.py -v`
Expected: FAIL : `TypeError: FillEvent.__init__() got an unexpected keyword argument 'commission'`

- [ ] **Step 7: 在 `FillEvent` 新增欄位**

In `04_paper_trading/events.py`, replace:

```python
@dataclass
class FillEvent:
    """execution_agent 確認成交"""

    symbol: str
    side: str
    quantity: float
    average_price: float
    order_id: str
```

with:

```python
@dataclass
class FillEvent:
    """execution_agent 確認成交"""

    symbol: str
    side: str
    quantity: float
    average_price: float
    order_id: str
    commission: float = 0.0  # 這筆訂單的總手續費, 從成交回應的 fills 陣列加總而得
    commission_asset: str = ""  # 手續費計價資產(例如 "USDT" 或 "BNB")
```

- [ ] **Step 8: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_events.py -v`
Expected: PASS (9 passed)

- [ ] **Step 9: Commit**

```bash
git add 04_paper_trading/events.py tests/test_paper_trading_events.py
git commit -m "feat: add computed_value/limit_value to RejectionEvent, commission fields to FillEvent"
```

---

### Task 2: `risk_agent.py` 抽出計算 helper, `check_*` 內部改用 helper

**Files:**
- Modify: `04_paper_trading/agents/risk_agent.py`
- Test: `tests/test_paper_trading_risk_agent.py`

**Interfaces:**
- Consumes: 無新依賴(純數值計算, `pandas`/`numpy` 已是既有 import).
- Produces: `compute_potential_loss_usdt(order_quantity, average_true_range, atr_stop_multiplier) -> float`、`compute_daily_loss_fraction(account_equity_usdt, day_start_equity_usdt) -> float`、`compute_max_correlation_against_existing_positions(candidate_close_price_series, existing_position_close_price_series) -> float | None`、`compute_staleness_detail(last_candle_open_time, current_time, bar_interval=timedelta(days=1), staleness_multiplier=1.5) -> dict`(含 `"time_since_close_seconds"`、`"threshold_seconds"` 兩個 key) : 供 Task 3 的 `review_portfolio` 呼叫.

- [ ] **Step 1: 寫失敗測試, 確認 `compute_potential_loss_usdt` 的計算結果**

Append to `tests/test_paper_trading_risk_agent.py`:

```python
def test_compute_potential_loss_usdt_matches_quantity_times_stop_distance():
    result = risk_agent.compute_potential_loss_usdt(
        order_quantity=0.03, average_true_range=1_000.0, atr_stop_multiplier=2.0
    )
    assert result == pytest.approx(60.0)  # 0.03 * 2 * 1000
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py -v`
Expected: FAIL : `AttributeError: module 'risk_agent' has no attribute 'compute_potential_loss_usdt'`

- [ ] **Step 3: 新增 `compute_potential_loss_usdt`, `check_max_loss_per_trade` 內部改用它**

In `04_paper_trading/agents/risk_agent.py`, replace:

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
```

with:

```python
def compute_potential_loss_usdt(
    order_quantity: float, average_true_range: float, atr_stop_multiplier: float
) -> float:
    """算出這筆開倉若觸及停損會虧損多少 USDT(數量 x 停損距離) , 與 check_max_loss_per_trade 內部算法相同"""
    return order_quantity * atr_stop_multiplier * average_true_range


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
    potential_loss_usdt = compute_potential_loss_usdt(
        order_quantity, average_true_range, atr_stop_multiplier
    )
    return potential_loss_usdt <= account_equity_usdt * max_loss_per_trade_fraction
```

- [ ] **Step 4: 執行測試確認通過, 並確認既有 3 個 `check_max_loss_per_trade` 測試仍通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py -k "potential_loss or max_loss_per_trade" -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 寫失敗測試, 確認 `compute_daily_loss_fraction` 的計算結果**

Append to `tests/test_paper_trading_risk_agent.py`:

```python
def test_compute_daily_loss_fraction_returns_zero_when_day_start_equity_non_positive():
    assert risk_agent.compute_daily_loss_fraction(9_000.0, 0.0) == 0.0


def test_compute_daily_loss_fraction_computes_correct_ratio():
    result = risk_agent.compute_daily_loss_fraction(9_500.0, 10_000.0)
    assert result == pytest.approx(0.05)
```

- [ ] **Step 6: 執行測試確認失敗**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py -v`
Expected: FAIL : `AttributeError: module 'risk_agent' has no attribute 'compute_daily_loss_fraction'`

- [ ] **Step 7: 新增 `compute_daily_loss_fraction`, `check_daily_circuit_breaker` 內部改用它**

In `04_paper_trading/agents/risk_agent.py`, replace:

```python
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
```

with:

```python
def compute_daily_loss_fraction(account_equity_usdt: float, day_start_equity_usdt: float) -> float:
    """算出當日虧損比例; 當日開始淨值為 0 或負值時視為無法判斷, 回傳 0.0(保守, 不誤判為熔斷)"""
    if day_start_equity_usdt <= 0:
        return 0.0
    return (day_start_equity_usdt - account_equity_usdt) / day_start_equity_usdt


def check_daily_circuit_breaker(
    account_equity_usdt: float,
    day_start_equity_usdt: float,
    max_daily_loss_fraction: float = 0.04,
) -> bool:
    """回傳 True 代表尚未觸發每日熔斷; 當日開始淨值為 0 或負值時視為無法判斷, 保守放行不誤擋"""
    if day_start_equity_usdt <= 0:
        return True
    return compute_daily_loss_fraction(account_equity_usdt, day_start_equity_usdt) <= max_daily_loss_fraction
```

- [ ] **Step 8: 執行測試確認通過, 並確認既有 3 個 `check_daily_circuit_breaker` 測試仍通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py -k "daily_loss_fraction or daily_circuit_breaker" -v`
Expected: PASS (5 passed)

- [ ] **Step 9: 寫失敗測試, 確認 `compute_max_correlation_against_existing_positions` 的 4 種情境**

Append to `tests/test_paper_trading_risk_agent.py`:

```python
def test_compute_max_correlation_returns_none_when_no_existing_positions():
    candidate_close_prices = pd.Series([100.0, 101.0, 102.0])
    assert risk_agent.compute_max_correlation_against_existing_positions(
        candidate_close_prices, {}
    ) is None


def test_compute_max_correlation_returns_none_when_insufficient_overlap():
    candidate_close_prices = pd.Series([100.0, 101.0])
    existing_close_prices = pd.Series([100.0, 101.0])
    assert risk_agent.compute_max_correlation_against_existing_positions(
        candidate_close_prices, {"ETHUSDT": existing_close_prices}
    ) is None


def test_compute_max_correlation_returns_none_when_correlation_is_nan():
    candidate_close_prices = pd.Series([100.0, 102.0, 99.0, 105.0])
    existing_close_prices = pd.Series([100.0, 100.0, 100.0, 100.0])
    assert risk_agent.compute_max_correlation_against_existing_positions(
        candidate_close_prices, {"ETHUSDT": existing_close_prices}
    ) is None


def test_compute_max_correlation_returns_highest_value_across_existing_positions():
    candidate_close_prices = pd.Series([100.0, 102.0, 99.0, 105.0, 110.0])
    highly_correlated_prices = candidate_close_prices * 2.0  # 相關係數 = 1.0
    negatively_correlated_prices = pd.Series([100.0, 98.0, 101.0, 95.0, 90.0])
    result = risk_agent.compute_max_correlation_against_existing_positions(
        candidate_close_prices,
        {"ETHUSDT": highly_correlated_prices, "SOLUSDT": negatively_correlated_prices},
    )
    assert result == pytest.approx(1.0)
```

- [ ] **Step 10: 執行測試確認失敗**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py -v`
Expected: FAIL : `AttributeError: module 'risk_agent' has no attribute 'compute_max_correlation_against_existing_positions'`

- [ ] **Step 11: 新增 `compute_max_correlation_against_existing_positions`, `check_correlation_limit` 內部改用它**

In `04_paper_trading/agents/risk_agent.py`, replace:

```python
def check_correlation_limit(
    candidate_close_price_series: pd.Series,
    existing_position_close_price_series: dict,
    max_correlation: float = 0.8,
) -> bool:
    """
    回傳 True 代表候選標的與所有現有持倉的日報酬率相關係數(correlation coefficient) 皆未超過上限,
    可以開倉. 任一現有持倉缺少至少 2 個重疊報酬率數據點, 或相關係數算出 NaN(例如某段價格完全不變) ,
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
        with np.errstate(invalid="ignore", divide="ignore"):
            correlation = aligned_candidate_returns.corr(aligned_existing_returns)
        if pd.isna(correlation) or correlation > max_correlation:
            return False
    return True
```

with:

```python
def compute_max_correlation_against_existing_positions(
    candidate_close_price_series: pd.Series, existing_position_close_price_series: dict
) -> float | None:
    """
    回傳候選標的與所有現有持倉中最高的日報酬率相關係數(correlation coefficient) . 無現有持倉時
    回傳 None(代表無需比較) . 任一現有持倉缺少至少 2 個重疊報酬率數據點, 或相關係數算出 NaN
    (例如某段價格完全不變) , 同樣回傳 None(代表數據不足以計算, 而非數值為 0) , 呼叫端應將 None
    視為無法確認風險, 保守處理
    """
    if not existing_position_close_price_series:
        return None
    candidate_returns = candidate_close_price_series.pct_change().dropna()
    correlations = []
    for existing_returns_series in existing_position_close_price_series.values():
        existing_returns = existing_returns_series.pct_change().dropna()
        overlapping_length = min(len(candidate_returns), len(existing_returns))
        if overlapping_length < 2:
            return None
        aligned_candidate_returns = candidate_returns.iloc[-overlapping_length:].reset_index(
            drop=True
        )
        aligned_existing_returns = existing_returns.iloc[-overlapping_length:].reset_index(
            drop=True
        )
        with np.errstate(invalid="ignore", divide="ignore"):
            correlation = aligned_candidate_returns.corr(aligned_existing_returns)
        if pd.isna(correlation):
            return None
        correlations.append(correlation)
    return max(correlations)


def check_correlation_limit(
    candidate_close_price_series: pd.Series,
    existing_position_close_price_series: dict,
    max_correlation: float = 0.8,
) -> bool:
    """
    回傳 True 代表候選標的與所有現有持倉的日報酬率相關係數(correlation coefficient) 皆未超過上限,
    可以開倉. 任一現有持倉缺少至少 2 個重疊報酬率數據點, 或相關係數算出 NaN(例如某段價格完全不變) ,
    視為無法確認風險, 直接回傳 False(風控規則寧可保守拒絕, 不因數據不足而放行)
    """
    if not existing_position_close_price_series:
        return True
    max_correlation_value = compute_max_correlation_against_existing_positions(
        candidate_close_price_series, existing_position_close_price_series
    )
    if max_correlation_value is None:
        return False
    return max_correlation_value <= max_correlation
```

- [ ] **Step 12: 執行測試確認通過, 並確認既有 5 個 `check_correlation_limit` 測試仍通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py -k "correlation" -v`
Expected: PASS (9 passed)

- [ ] **Step 13: 寫失敗測試, 確認 `compute_staleness_detail` 的計算結果**

Append to `tests/test_paper_trading_risk_agent.py`:

```python
def test_compute_staleness_detail_returns_seconds_since_close_and_threshold():
    current_time = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    last_candle_open_time = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)  # 24 小時前開盤
    detail = risk_agent.compute_staleness_detail(
        last_candle_open_time, current_time, timedelta(days=1), 1.5
    )
    # 約略收盤時間 = 開盤 + 1 天 = 2026-07-06 12:00, 與 current_time 完全相同, 已過期 0 秒
    assert detail["time_since_close_seconds"] == pytest.approx(0.0)
    assert detail["threshold_seconds"] == pytest.approx(timedelta(days=1.5).total_seconds())
```

- [ ] **Step 14: 執行測試確認失敗**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py -v`
Expected: FAIL : `AttributeError: module 'risk_agent' has no attribute 'compute_staleness_detail'`

- [ ] **Step 15: 新增 `compute_staleness_detail`, `check_data_staleness` 內部改用它**

In `04_paper_trading/agents/risk_agent.py`, replace:

```python
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

with:

```python
def compute_staleness_detail(
    last_candle_open_time: datetime,
    current_time: datetime,
    bar_interval: timedelta = timedelta(days=1),
    staleness_multiplier: float = 1.5,
) -> dict:
    """
    回傳 {"time_since_close_seconds": 已過期秒數(可能為負, 代表尚未到約略收盤時間) ,
    "threshold_seconds": 門檻秒數}, 與 check_data_staleness 的計算邏輯相同, 供
    run_once.py 記錄過期細節用
    """
    approximate_close_time = last_candle_open_time + bar_interval
    time_since_close = current_time - approximate_close_time
    threshold = bar_interval * staleness_multiplier
    return {
        "time_since_close_seconds": time_since_close.total_seconds(),
        "threshold_seconds": threshold.total_seconds(),
    }


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
    detail = compute_staleness_detail(
        last_candle_open_time, current_time, bar_interval, staleness_multiplier
    )
    return detail["time_since_close_seconds"] <= detail["threshold_seconds"]
```

Note: leave the pre-existing docstring's `「」` characters as-is in this replacement (this is untouched legacy text being carried over, not new text this task authors); do not introduce any new `「」` or `—` characters in the new docstrings you write.

- [ ] **Step 16: 執行測試確認通過, 並確認既有 3 個 `check_data_staleness` 測試仍通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py -k "staleness" -v`
Expected: PASS (4 passed)

- [ ] **Step 17: 執行整份 `risk_agent` 測試檔案確認全部通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py -v`
Expected: PASS (所有既有測試 + 本任務新增的 13 個測試全部通過)

- [ ] **Step 18: Commit**

```bash
git add 04_paper_trading/agents/risk_agent.py tests/test_paper_trading_risk_agent.py
git commit -m "feat: extract pure calculation helpers in risk_agent, check_* bool contracts unchanged"
```

---

### Task 3: `risk_agent.py` : `review_portfolio` 記錄拒絕數值, `stale_symbols` 改用 `dict`

**Files:**
- Modify: `04_paper_trading/agents/risk_agent.py`
- Test: `tests/test_paper_trading_risk_agent.py`

**Interfaces:**
- Consumes: Task 1 的 `RejectionEvent(symbol, reason, computed_value, limit_value)`; Task 2 的 `compute_daily_loss_fraction`、`compute_potential_loss_usdt`、`compute_max_correlation_against_existing_positions`.
- Produces: `review_portfolio(signal_events, stale_symbols: dict, current_base_asset_balances, account_equity_usdt, day_start_equity_usdt, close_price_histories, engine_parameters, risk_limits) -> dict` : `stale_symbols` 參數型別從 `list` 改為 `dict[str, dict]`(標的 → `compute_staleness_detail` 回傳的字典), 供 Task 5 的 `run_once.py` 呼叫.

- [ ] **Step 1: 把既有測試裡所有 `review_portfolio(...)` 呼叫的 `stale_symbols` 引數從 `list` 改成 `dict`**

In `tests/test_paper_trading_risk_agent.py`, every call to `risk_agent.review_portfolio(...)` currently passes `signal_events, [], ...` as the first two positional arguments (the second one is the `stale_symbols` parameter, an empty list literal, in 8 separate test functions). Replace every occurrence of the exact substring:

```
signal_events, [],
```

with:

```
signal_events, {},
```

This is a pure find-and-replace across the file (8 occurrences); it does not change any test's behavior since an empty list and an empty dict iterate identically in the code under test. Do not touch the one remaining call in `test_review_portfolio_marks_stale_symbol_as_rejected_and_other_proceeds` yet : it uses `["ETHUSDT"]`, not `[]`, and is handled in Step 2.

- [ ] **Step 2: 寫失敗測試, 更新過期標的的拒絕情境為 `dict` 型別並斷言數值**

In `tests/test_paper_trading_risk_agent.py`, replace:

```python
def test_review_portfolio_marks_stale_symbol_as_rejected_and_other_proceeds():
    signal_events = {"BTCUSDT": _make_signal_event("BTCUSDT", target_position=0)}

    decisions = risk_agent.review_portfolio(
        signal_events, ["ETHUSDT"], {}, 10_000.0, 10_000.0, {}, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "過期" in decisions["ETHUSDT"].reason
    assert decisions["BTCUSDT"] is None
```

with:

```python
def test_review_portfolio_marks_stale_symbol_as_rejected_and_other_proceeds():
    signal_events = {"BTCUSDT": _make_signal_event("BTCUSDT", target_position=0)}
    stale_symbols = {"ETHUSDT": {"time_since_close_seconds": 200_000.0, "threshold_seconds": 129_600.0}}

    decisions = risk_agent.review_portfolio(
        signal_events, stale_symbols, {}, 10_000.0, 10_000.0, {}, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "過期" in decisions["ETHUSDT"].reason
    assert decisions["ETHUSDT"].computed_value == pytest.approx(200_000.0)
    assert decisions["ETHUSDT"].limit_value == pytest.approx(129_600.0)
    assert decisions["BTCUSDT"] is None
```

- [ ] **Step 3: 執行測試確認失敗**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py::test_review_portfolio_marks_stale_symbol_as_rejected_and_other_proceeds -v`
Expected: FAIL : `AssertionError: assert None == pytest.approx(200000.0)`(`computed_value` 目前恆為 `None`)

- [ ] **Step 4: 修改 `review_portfolio` 的數據過期段落, 讀取 `stale_symbols` 字典的細節**

In `04_paper_trading/agents/risk_agent.py`, replace:

```python
    for symbol in stale_symbols:
        decisions[symbol] = RejectionEvent(symbol=symbol, reason="數據已過期, 暫停信號生成")
```

with:

```python
    for symbol in stale_symbols:
        decisions[symbol] = RejectionEvent(
            symbol=symbol,
            reason="數據已過期, 暫停信號生成",
            computed_value=stale_symbols[symbol]["time_since_close_seconds"],
            limit_value=stale_symbols[symbol]["threshold_seconds"],
        )
```

- [ ] **Step 5: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py::test_review_portfolio_marks_stale_symbol_as_rejected_and_other_proceeds -v`
Expected: PASS

- [ ] **Step 6: 寫失敗測試, 確認每日熔斷拒絕情境附上數值**

In `tests/test_paper_trading_risk_agent.py`, replace:

```python
def test_review_portfolio_circuit_breaker_rejects_all_symbols():
    signal_events = {
        "BTCUSDT": _make_signal_event("BTCUSDT", target_position=1),
        "ETHUSDT": _make_signal_event("ETHUSDT", target_position=0),
    }

    decisions = risk_agent.review_portfolio(
        signal_events, {}, {}, 9_500.0, 10_000.0, {}, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["BTCUSDT"], RejectionEvent)
    assert "熔斷" in decisions["BTCUSDT"].reason
    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "熔斷" in decisions["ETHUSDT"].reason
```

with:

```python
def test_review_portfolio_circuit_breaker_rejects_all_symbols():
    signal_events = {
        "BTCUSDT": _make_signal_event("BTCUSDT", target_position=1),
        "ETHUSDT": _make_signal_event("ETHUSDT", target_position=0),
    }

    decisions = risk_agent.review_portfolio(
        signal_events, {}, {}, 9_500.0, 10_000.0, {}, ENGINE_PARAMETERS, RISK_LIMITS
    )

    assert isinstance(decisions["BTCUSDT"], RejectionEvent)
    assert "熔斷" in decisions["BTCUSDT"].reason
    assert decisions["BTCUSDT"].computed_value == pytest.approx(0.05)  # (10000-9500)/10000
    assert decisions["BTCUSDT"].limit_value == pytest.approx(0.04)
    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "熔斷" in decisions["ETHUSDT"].reason
    assert decisions["ETHUSDT"].computed_value == pytest.approx(0.05)
    assert decisions["ETHUSDT"].limit_value == pytest.approx(0.04)
```

- [ ] **Step 7: 執行測試確認失敗**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py::test_review_portfolio_circuit_breaker_rejects_all_symbols -v`
Expected: FAIL : `AssertionError: assert None == pytest.approx(0.05)`

- [ ] **Step 8: 修改 `review_portfolio` 的熔斷段落, 附上數值**

In `04_paper_trading/agents/risk_agent.py`, replace:

```python
    circuit_breaker_ok = check_daily_circuit_breaker(
        account_equity_usdt, day_start_equity_usdt, risk_limits["max_daily_loss_fraction"]
    )
    if not circuit_breaker_ok:
        for symbol in ordered_symbols + list(stale_symbols):
            decisions[symbol] = RejectionEvent(
                symbol=symbol, reason="每日虧損熔斷已觸發, 停止當日所有交易"
            )
        return decisions
```

with:

```python
    circuit_breaker_ok = check_daily_circuit_breaker(
        account_equity_usdt, day_start_equity_usdt, risk_limits["max_daily_loss_fraction"]
    )
    if not circuit_breaker_ok:
        daily_loss_fraction = compute_daily_loss_fraction(account_equity_usdt, day_start_equity_usdt)
        for symbol in ordered_symbols + list(stale_symbols):
            decisions[symbol] = RejectionEvent(
                symbol=symbol,
                reason="每日虧損熔斷已觸發, 停止當日所有交易",
                computed_value=daily_loss_fraction,
                limit_value=risk_limits["max_daily_loss_fraction"],
            )
        return decisions
```

- [ ] **Step 9: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py::test_review_portfolio_circuit_breaker_rejects_all_symbols -v`
Expected: PASS

- [ ] **Step 10: 寫失敗測試, 確認單筆潛在虧損超限附上數值**

In `tests/test_paper_trading_risk_agent.py`, replace:

```python
    assert isinstance(decisions["BTCUSDT"], RejectionEvent)
    assert "潛在虧損" in decisions["BTCUSDT"].reason


def test_review_portfolio_rejects_buy_when_max_concurrent_positions_reached():
```

with:

```python
    assert isinstance(decisions["BTCUSDT"], RejectionEvent)
    assert "潛在虧損" in decisions["BTCUSDT"].reason
    # 潛在虧損 = 0.05(buy_quantity, 1%風險比例算出) * 2.0 * 1000 = 100, 佔淨值比例 = 100/10000 = 0.01
    assert decisions["BTCUSDT"].computed_value == pytest.approx(0.01)
    assert decisions["BTCUSDT"].limit_value == pytest.approx(0.005)


def test_review_portfolio_rejects_buy_when_max_concurrent_positions_reached():
```

- [ ] **Step 11: 執行測試確認失敗**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py::test_review_portfolio_rejects_buy_when_max_loss_per_trade_exceeded -v`
Expected: FAIL : `AssertionError: assert None == pytest.approx(0.01)`

- [ ] **Step 12: 修改 `review_portfolio` 的單筆潛在虧損段落, 附上數值**

In `04_paper_trading/agents/risk_agent.py`, replace:

```python
        if not check_max_loss_per_trade(
            buy_quantity,
            signal_event.latest_average_true_range,
            engine_parameters["atr_stop_multiplier"],
            account_equity_usdt,
            risk_limits["max_loss_per_trade_fraction"],
        ):
            decisions[symbol] = RejectionEvent(symbol=symbol, reason="單筆潛在虧損超過風控上限")
            continue
```

with:

```python
        if not check_max_loss_per_trade(
            buy_quantity,
            signal_event.latest_average_true_range,
            engine_parameters["atr_stop_multiplier"],
            account_equity_usdt,
            risk_limits["max_loss_per_trade_fraction"],
        ):
            potential_loss_usdt = compute_potential_loss_usdt(
                buy_quantity, signal_event.latest_average_true_range, engine_parameters["atr_stop_multiplier"]
            )
            decisions[symbol] = RejectionEvent(
                symbol=symbol,
                reason="單筆潛在虧損超過風控上限",
                computed_value=potential_loss_usdt / account_equity_usdt,
                limit_value=risk_limits["max_loss_per_trade_fraction"],
            )
            continue
```

- [ ] **Step 13: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py::test_review_portfolio_rejects_buy_when_max_loss_per_trade_exceeded -v`
Expected: PASS

- [ ] **Step 14: 寫失敗測試, 確認最大同時持倉數超限附上數值**

In `tests/test_paper_trading_risk_agent.py`, replace:

```python
    assert decisions["BTCUSDT"] is None  # 已是多單, 目標與當前相同
    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "持倉數" in decisions["ETHUSDT"].reason
```

with:

```python
    assert decisions["BTCUSDT"] is None  # 已是多單, 目標與當前相同
    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "持倉數" in decisions["ETHUSDT"].reason
    assert decisions["ETHUSDT"].computed_value == 1  # BTCUSDT 已是持倉, 計入同類別持倉數
    assert decisions["ETHUSDT"].limit_value == 1
```

- [ ] **Step 15: 執行測試確認失敗**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py::test_review_portfolio_rejects_buy_when_max_concurrent_positions_reached -v`
Expected: FAIL : `AssertionError: assert None == 1`

- [ ] **Step 16: 修改 `review_portfolio` 的最大同時持倉數段落, 附上數值**

In `04_paper_trading/agents/risk_agent.py`, replace:

```python
        if not check_max_concurrent_positions(
            positions_in_same_market_count, market_type, risk_limits["max_positions_by_market"]
        ):
            decisions[symbol] = RejectionEvent(
                symbol=symbol, reason=f"已達 {market_type} 類別最大同時持倉數上限"
            )
            continue
```

with:

```python
        if not check_max_concurrent_positions(
            positions_in_same_market_count, market_type, risk_limits["max_positions_by_market"]
        ):
            decisions[symbol] = RejectionEvent(
                symbol=symbol,
                reason=f"已達 {market_type} 類別最大同時持倉數上限",
                computed_value=positions_in_same_market_count,
                limit_value=risk_limits["max_positions_by_market"][market_type],
            )
            continue
```

- [ ] **Step 17: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py::test_review_portfolio_rejects_buy_when_max_concurrent_positions_reached -v`
Expected: PASS

- [ ] **Step 18: 寫失敗測試, 確認相關係數超限與無法計算兩種情境各自附上數值**

In `tests/test_paper_trading_risk_agent.py`, replace:

```python
    assert isinstance(decisions["BTCUSDT"], OrderEvent)  # 依固定順序先處理, 當時尚無現有持倉可比較
    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "相關係數" in decisions["ETHUSDT"].reason


def test_review_portfolio_processes_symbols_in_symbol_market_types_order_not_dict_order():
```

with:

```python
    assert isinstance(decisions["BTCUSDT"], OrderEvent)  # 依固定順序先處理, 當時尚無現有持倉可比較
    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "相關係數" in decisions["ETHUSDT"].reason
    assert decisions["ETHUSDT"].computed_value == pytest.approx(1.0)  # 純比例縮放, 相關係數為 1.0
    assert decisions["ETHUSDT"].limit_value == pytest.approx(0.8)


def test_review_portfolio_rejects_buy_when_correlation_cannot_be_computed():
    # BTC 的訊號目標倉位與當前實際倉位相同(target_position=1, 已持有 0.05 顆), 所以 BTC 自己會在
    # 目標倉位比對這一步就得到 None, 不消耗任何開倉方向檢查, 但仍會被計入 open_long_symbols,
    # 成為 ETH 開倉時的比較基準; BTC 價格完全不變, 報酬率全為 0, 相關係數無法定義(NaN),
    # ETH 應被保守拒絕, 且與相關係數真的超過上限這種情況用不同的 reason 文字,
    # computed_value 應為 None(無法計算, 而非 0)
    signal_events = {
        "BTCUSDT": _make_signal_event(
            "BTCUSDT", target_position=1, close_price=50_000.0, average_true_range=1_000.0
        ),
        "ETHUSDT": _make_signal_event(
            "ETHUSDT", target_position=1, close_price=3_000.0, average_true_range=100.0
        ),
    }
    current_base_asset_balances = {"BTCUSDT": 0.05}  # 市值 2500 USDT, 與 target_position=1 相符
    close_price_histories = {
        "BTCUSDT": _make_close_price_series([50_000.0] * 30),  # 價格完全不變
        "ETHUSDT": _make_close_price_series([3_000.0 + index * 10 for index in range(30)]),
    }

    decisions = risk_agent.review_portfolio(
        signal_events, {}, current_base_asset_balances, 12_500.0, 12_500.0,
        close_price_histories, ENGINE_PARAMETERS, RISK_LIMITS,
    )

    assert decisions["BTCUSDT"] is None  # 已是多單, 目標與當前相同, 不消耗任何風控檢查
    assert isinstance(decisions["ETHUSDT"], RejectionEvent)
    assert "無法計算" in decisions["ETHUSDT"].reason
    assert decisions["ETHUSDT"].computed_value is None
    assert decisions["ETHUSDT"].limit_value == pytest.approx(0.8)


def test_review_portfolio_processes_symbols_in_symbol_market_types_order_not_dict_order():
```

- [ ] **Step 19: 執行測試確認失敗**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py -k "correlation" -v`
Expected: FAIL : `test_review_portfolio_rejects_second_correlated_open_in_same_batch` 因 `computed_value` 仍是 `None` 而失敗; `test_review_portfolio_rejects_buy_when_correlation_cannot_be_computed` 因 reason 文字不含 "無法計算" 而失敗(目前兩種情況共用同一句 reason)

- [ ] **Step 20: 修改 `review_portfolio` 的相關性段落, 拆成兩種 reason 並附上數值**

In `04_paper_trading/agents/risk_agent.py`, replace:

```python
        if not check_correlation_limit(
            close_price_histories[symbol],
            existing_position_close_price_series,
            risk_limits["max_correlation"],
        ):
            decisions[symbol] = RejectionEvent(symbol=symbol, reason="與現有持倉相關係數超過風控上限")
            continue
```

with:

```python
        if not check_correlation_limit(
            close_price_histories[symbol],
            existing_position_close_price_series,
            risk_limits["max_correlation"],
        ):
            max_correlation_value = compute_max_correlation_against_existing_positions(
                close_price_histories[symbol], existing_position_close_price_series
            )
            if max_correlation_value is None:
                decisions[symbol] = RejectionEvent(
                    symbol=symbol,
                    reason="相關係數無法計算(數據不足或無變化), 風控保守拒絕",
                    computed_value=None,
                    limit_value=risk_limits["max_correlation"],
                )
            else:
                decisions[symbol] = RejectionEvent(
                    symbol=symbol,
                    reason="與現有持倉相關係數超過風控上限",
                    computed_value=max_correlation_value,
                    limit_value=risk_limits["max_correlation"],
                )
            continue
```

- [ ] **Step 21: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py -k "correlation" -v`
Expected: PASS

- [ ] **Step 22: 寫失敗測試, 確認買進名目金額超限附上數值**

In `tests/test_paper_trading_risk_agent.py`, replace:

```python
    assert isinstance(decisions["BTCUSDT"], RejectionEvent)
    assert "超過風控上限" in decisions["BTCUSDT"].reason
```

with:

```python
    assert isinstance(decisions["BTCUSDT"], RejectionEvent)
    assert "超過風控上限" in decisions["BTCUSDT"].reason
    assert decisions["BTCUSDT"].computed_value == pytest.approx(2_500.0)  # buy_quantity(0.05) * 50000
    assert decisions["BTCUSDT"].limit_value == pytest.approx(1_000.0)  # initial_capital(1000) * max_position_fraction(1.0)
```

- [ ] **Step 23: 執行測試確認失敗**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py::test_review_portfolio_rejects_buy_when_notional_exceeds_cap -v`
Expected: FAIL : `AssertionError: assert None == pytest.approx(2500.0)`

- [ ] **Step 24: 修改 `review_portfolio` 的名目金額段落, 附上數值(字串維持不變, 額外附結構化欄位)**

In `04_paper_trading/agents/risk_agent.py`, replace:

```python
        if notional_value_usdt > maximum_allowed_notional_usdt:
            decisions[symbol] = RejectionEvent(
                symbol=symbol,
                reason=(
                    f"買進名目金額 {notional_value_usdt:.2f} USDT 超過風控上限 "
                    f"{maximum_allowed_notional_usdt:.2f} USDT"
                ),
            )
            continue
```

with:

```python
        if notional_value_usdt > maximum_allowed_notional_usdt:
            decisions[symbol] = RejectionEvent(
                symbol=symbol,
                reason=(
                    f"買進名目金額 {notional_value_usdt:.2f} USDT 超過風控上限 "
                    f"{maximum_allowed_notional_usdt:.2f} USDT"
                ),
                computed_value=notional_value_usdt,
                limit_value=maximum_allowed_notional_usdt,
            )
            continue
```

- [ ] **Step 25: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py::test_review_portfolio_rejects_buy_when_notional_exceeds_cap -v`
Expected: PASS

- [ ] **Step 26: 執行整份 `risk_agent` 測試檔案與全專案測試, 確認無回歸**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_risk_agent.py -v && python3 -m pytest tests/ -v`
Expected: PASS(全部通過, 無回歸)

- [ ] **Step 27: Commit**

```bash
git add 04_paper_trading/agents/risk_agent.py tests/test_paper_trading_risk_agent.py
git commit -m "feat: attach computed_value/limit_value to all review_portfolio rejection reasons"
```

---

### Task 4: `execution_agent.py` 解析手續費

**Files:**
- Modify: `04_paper_trading/agents/execution_agent.py`
- Test: `tests/test_paper_trading_execution_agent.py`

**Interfaces:**
- Consumes: Task 1 的 `FillEvent(symbol, side, quantity, average_price, order_id, commission, commission_asset)`.
- Produces: 無新的對外函式, `execute()` 回傳的 `FillEvent` 多了正確填入的 `commission`/`commission_asset`.

- [ ] **Step 1: 在測試檔案新增 `import pytest`(供 `pytest.approx` 使用)**

In `tests/test_paper_trading_execution_agent.py`, replace:

```python
"""execution_agent.execute 的單元測試 — monkeypatch 掉 binance_testnet_client 的真實網路呼叫"""
import requests

import execution_agent
from events import FailEvent, FillEvent, OrderEvent
```

with:

```python
"""execution_agent.execute 的單元測試 — monkeypatch 掉 binance_testnet_client 的真實網路呼叫"""
import pytest
import requests

import execution_agent
from events import FailEvent, FillEvent, OrderEvent
```

- [ ] **Step 2: 寫失敗測試, 確認 `fills` 陣列存在時手續費正確加總**

Append to `tests/test_paper_trading_execution_agent.py`:

```python
def test_execute_computes_total_commission_from_fills(monkeypatch):
    order_event = OrderEvent(symbol="BTCUSDT", side="BUY", quantity=0.05)
    monkeypatch.setattr(
        execution_agent,
        "place_market_order",
        lambda symbol, side, quantity: (
            200,
            {
                "orderId": 123,
                "status": "FILLED",
                "executedQty": "0.0500",
                "cummulativeQuoteQty": "2500.00",
                "fills": [
                    {"price": "50000.00", "qty": "0.0300", "commission": "1.500", "commissionAsset": "USDT"},
                    {"price": "50000.00", "qty": "0.0200", "commission": "1.000", "commissionAsset": "USDT"},
                ],
            },
        ),
    )

    result = execution_agent.execute(order_event, SYMBOL_FILTERS)

    assert isinstance(result, FillEvent)
    assert result.commission == pytest.approx(2.5)
    assert result.commission_asset == "USDT"


def test_execute_defaults_commission_to_zero_when_fills_missing(monkeypatch):
    order_event = OrderEvent(symbol="BTCUSDT", side="BUY", quantity=0.05)
    monkeypatch.setattr(
        execution_agent,
        "place_market_order",
        lambda symbol, side, quantity: (
            200,
            {
                "orderId": 123,
                "status": "FILLED",
                "executedQty": "0.0500",
                "cummulativeQuoteQty": "2500.00",
            },
        ),
    )

    result = execution_agent.execute(order_event, SYMBOL_FILTERS)

    assert result.commission == 0.0
    assert result.commission_asset == ""
```

- [ ] **Step 3: 執行測試確認第一個新測試失敗, 第二個新測試已通過(因為現有程式碼本來就不填這兩個欄位, 預設值恰好是 0.0/"")**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_execution_agent.py -k "commission" -v`
Expected: `test_execute_computes_total_commission_from_fills` FAIL(`assert 0.0 == pytest.approx(2.5)`), `test_execute_defaults_commission_to_zero_when_fills_missing` PASS

- [ ] **Step 4: 新增 `_compute_total_commission`, `execute()` 填入 `FillEvent` 的手續費欄位**

In `04_paper_trading/agents/execution_agent.py`, replace:

```python
def _compute_average_fill_price(order_status_response: dict) -> float:
    """用累計成交金額除以累計成交數量, 得到這筆市價單的加權平均成交價"""
    executed_quantity = float(order_status_response["executedQty"])
    cumulative_quote_quantity = float(order_status_response["cummulativeQuoteQty"])
    return cumulative_quote_quantity / executed_quantity
```

with:

```python
def _compute_average_fill_price(order_status_response: dict) -> float:
    """用累計成交金額除以累計成交數量, 得到這筆市價單的加權平均成交價"""
    executed_quantity = float(order_status_response["executedQty"])
    cumulative_quote_quantity = float(order_status_response["cummulativeQuoteQty"])
    return cumulative_quote_quantity / executed_quantity


def _compute_total_commission(order_status_response: dict) -> tuple[float, str]:
    """
    加總成交回應 fills 陣列裡每筆的 commission, 回傳 (加總後手續費, 手續費計價資產) .
    已知簡化 : 假設同一筆訂單裡所有 fills 的 commissionAsset 一致(實務上單一訂單極少見混用計價
    資產), 直接取第一筆 fill 的 commissionAsset, 不逐筆比對是否一致. fills 陣列不存在或為空時
    回傳 (0.0, "")
    """
    fills = order_status_response.get("fills", [])
    if not fills:
        return 0.0, ""
    total_commission = sum(float(fill["commission"]) for fill in fills)
    commission_asset = fills[0]["commissionAsset"]
    return total_commission, commission_asset
```

Then, in the same file, replace:

```python
        if current_status == "FILLED":
            return FillEvent(
                symbol=order_event.symbol,
                side=order_event.side,
                quantity=float(order_status_response["executedQty"]),
                average_price=_compute_average_fill_price(order_status_response),
                order_id=str(order_id),
            )
```

with:

```python
        if current_status == "FILLED":
            total_commission, commission_asset = _compute_total_commission(order_status_response)
            return FillEvent(
                symbol=order_event.symbol,
                side=order_event.side,
                quantity=float(order_status_response["executedQty"]),
                average_price=_compute_average_fill_price(order_status_response),
                order_id=str(order_id),
                commission=total_commission,
                commission_asset=commission_asset,
            )
```

- [ ] **Step 5: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_execution_agent.py -v`
Expected: PASS(全部通過, 含既有 9 個測試 + 本任務新增 2 個測試)

- [ ] **Step 6: Commit**

```bash
git add 04_paper_trading/agents/execution_agent.py tests/test_paper_trading_execution_agent.py
git commit -m "feat: parse commission from Binance fills array into FillEvent"
```

---

### Task 5: `run_once.py` 新增帳戶淨值/參數快照/訊號上下文, `stale_symbols` 改用 `dict`

**Files:**
- Modify: `04_paper_trading/run_once.py`
- Test: `tests/test_paper_trading_run_once.py`

**Interfaces:**
- Consumes: Task 2 的 `risk_agent.compute_staleness_detail(last_candle_open_time, current_time, bar_interval)`; Task 3 的 `risk_agent.review_portfolio(signal_events, stale_symbols: dict, ...)`.
- Produces: `run_once()` 回傳的 `record` 新增頂層欄位 `account_equity_usdt`、`day_start_equity_usdt`、`risk_limits`、`engine_parameters`; 每個標的的 `record["symbols"][symbol]` 若該標的存在於 `signal_events`, 新增 `signal`、`current_base_asset_balance` 兩個子欄位; `record["stale_symbols"]` 型別從 `list` 改為 `dict`.

- [ ] **Step 1: 寫失敗測試, 確認 `record` 新增頂層欄位與每個標的的訊號上下文**

Append to `tests/test_paper_trading_run_once.py`:

```python
def test_run_once_records_equity_snapshot_and_signal_context(tmp_path, monkeypatch):
    _patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        run_once.data_agent, "fetch_latest_candles", lambda symbol: _make_ohlcv_dataframe()
    )
    monkeypatch.setattr(
        run_once.signal_agent, "decide", lambda ohlcv_dataframe, symbol: _make_signal_event(symbol, 1)
    )
    monkeypatch.setattr(
        run_once.binance_testnet_client,
        "get_account_balances",
        lambda: {"BTC": 0.01, "USDT": 10_000.0},
    )
    monkeypatch.setattr(
        run_once.risk_agent, "review_portfolio", lambda *args, **kwargs: {"BTCUSDT": None}
    )

    record = run_once.run_once(symbols=["BTCUSDT"])

    expected_equity = 10_000.0 + 0.01 * 50_000.0
    assert record["account_equity_usdt"] == pytest.approx(expected_equity)
    assert record["day_start_equity_usdt"] == pytest.approx(expected_equity)
    assert record["risk_limits"] == run_once.RISK_LIMITS
    assert record["engine_parameters"] == run_once.signal_agent.FROZEN_ENGINE_PARAMETERS
    assert record["symbols"]["BTCUSDT"]["signal"]["target_position"] == 1
    assert record["symbols"]["BTCUSDT"]["signal"]["latest_close_price"] == 50_000.0
    assert record["symbols"]["BTCUSDT"]["signal"]["latest_average_true_range"] == 1_000.0
    assert record["symbols"]["BTCUSDT"]["current_base_asset_balance"] == 0.01
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_run_once.py::test_run_once_records_equity_snapshot_and_signal_context -v`
Expected: FAIL : `KeyError: 'account_equity_usdt'`

- [ ] **Step 3: 在 `run_once()` 新增頂層欄位與每個標的的訊號上下文**

In `04_paper_trading/run_once.py`, replace:

```python
    record["fetch_failures"] = fetch_failures
    record["stale_symbols"] = stale_symbols
```

with:

```python
    record["account_equity_usdt"] = account_equity_usdt
    record["day_start_equity_usdt"] = day_start_equity_usdt
    record["risk_limits"] = RISK_LIMITS
    record["engine_parameters"] = signal_agent.FROZEN_ENGINE_PARAMETERS
    record["fetch_failures"] = fetch_failures
    record["stale_symbols"] = stale_symbols
```

Then, in the same file, replace:

```python
    for symbol, decision in decisions.items():
        symbol_record = {"risk_decision": _serialize_event(decision)}
        if isinstance(decision, OrderEvent):
```

with:

```python
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
            symbol_record["current_base_asset_balance"] = current_base_asset_balances[symbol]
        if isinstance(decision, OrderEvent):
```

- [ ] **Step 4: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_run_once.py::test_run_once_records_equity_snapshot_and_signal_context -v`
Expected: PASS

- [ ] **Step 5: 寫失敗測試, 確認過期標的改用 `dict` 並附上 staleness 細節**

Append to `tests/test_paper_trading_run_once.py`:

```python
def test_run_once_records_stale_symbol_detail_as_dict(tmp_path, monkeypatch):
    _patch_common(monkeypatch, tmp_path)
    stale_open_time = pd.Timestamp.now(tz="UTC").tz_localize(None) - pd.Timedelta(days=10)
    stale_ohlcv_dataframe = pd.DataFrame(
        {
            "open_time": [stale_open_time],
            "open": [50_000.0],
            "high": [50_100.0],
            "low": [49_900.0],
            "close": [50_000.0],
            "volume": [10.0],
        }
    )
    monkeypatch.setattr(
        run_once.data_agent, "fetch_latest_candles", lambda symbol: stale_ohlcv_dataframe
    )
    monkeypatch.setattr(
        run_once.binance_testnet_client,
        "get_account_balances",
        lambda: {"BTC": 0.0, "USDT": 10_000.0},
    )
    monkeypatch.setattr(
        run_once.risk_agent, "review_portfolio", lambda *args, **kwargs: {"BTCUSDT": None}
    )

    record = run_once.run_once(symbols=["BTCUSDT"])

    assert isinstance(record["stale_symbols"], dict)
    assert "BTCUSDT" in record["stale_symbols"]
    assert record["stale_symbols"]["BTCUSDT"]["time_since_close_seconds"] > 0
    assert record["stale_symbols"]["BTCUSDT"]["threshold_seconds"] == pytest.approx(
        run_once.BAR_INTERVAL.total_seconds() * 1.5
    )
```

- [ ] **Step 6: 執行測試確認失敗**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_run_once.py::test_run_once_records_stale_symbol_detail_as_dict -v`
Expected: FAIL : `AssertionError: assert isinstance([], dict)`(目前 `stale_symbols` 仍是 `list`, 只存標的名稱)

- [ ] **Step 7: 把 `run_once()` 的 `stale_symbols` 從 `list` 改成 `dict`, 記錄過期細節**

In `04_paper_trading/run_once.py`, replace:

```python
    signal_events = {}
    stale_symbols = []
    close_price_histories = {}
```

with:

```python
    signal_events = {}
    stale_symbols = {}
    close_price_histories = {}
```

Then, in the same file, replace:

```python
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
```

with:

```python
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
```

- [ ] **Step 8: 執行測試確認通過**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_run_once.py::test_run_once_records_stale_symbol_detail_as_dict -v`
Expected: PASS

- [ ] **Step 9: 執行整份 `run_once` 測試檔案與全專案測試, 確認無回歸**

Run: `cd /home/ubuntu/jerome/quant-trading-system && python3 -m pytest tests/test_paper_trading_run_once.py -v && python3 -m pytest tests/ -v`
Expected: PASS(全部通過, 無回歸)

- [ ] **Step 10: Commit**

```bash
git add 04_paper_trading/run_once.py tests/test_paper_trading_run_once.py
git commit -m "feat: record equity snapshot, parameter snapshot, and signal context in run_once record"
```

---

## Self-Review

**Spec coverage:**
- Tier 1(帳戶淨值)、Tier 5(參數快照) → Task 5 Step 3
- Tier 2(訊號上下文) → Task 5 Step 3(`signal`、`current_base_asset_balance`)
- Tier 3(手續費) → Task 4
- Tier 4(風控數值化, 6 種拒絕情境 + `stale_symbols` 改 dict) → Task 2(4 個 helper) + Task 3(`review_portfolio` 全部 6 種情境 + dict 遷移)
- `RejectionEvent`/`FillEvent` 向下相容欄位 → Task 1
- 既有 `check_*` bool 合約不變 → Task 2 每個 Step 都保留既有測試並額外執行確認
- 測試計劃(既有測試不用重寫, 新增獨立單元測試, 全專案回歸) → 每個 Task 最後都有全量測試執行 Step

**Placeholder scan:** 無 "TBD" / "類似 Task N" / 未展開程式碼的步驟, 每個 Step 都有完整程式碼、指令與預期輸出.

**Type consistency:** `compute_staleness_detail` 回傳的兩個 key(`time_since_close_seconds`、`threshold_seconds`) 在 Task 2 定義, Task 3(`review_portfolio` 讀取 `stale_symbols[symbol]["time_since_close_seconds"]`)與 Task 5(`run_once.py` 呼叫並寫入 `record["stale_symbols"][symbol]`)三處用字完全一致; `compute_max_correlation_against_existing_positions`、`compute_potential_loss_usdt`、`compute_daily_loss_fraction` 的函式名稱與參數順序在 Task 2 定義後, Task 3 呼叫時完全一致; `RejectionEvent`/`FillEvent` 的新欄位名稱(`computed_value`、`limit_value`、`commission`、`commission_asset`)在 Task 1 定義後, Task 3/4 使用時完全一致.
