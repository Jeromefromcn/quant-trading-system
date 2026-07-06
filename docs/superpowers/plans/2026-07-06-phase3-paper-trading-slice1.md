# Phase 3 紙上交易 (paper trading) Slice 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 跑通一次最小可行的紙上交易 pipeline (data agent → signal agent → risk agent → execution agent) , 用凍結不變的 exp_002 策略, 對 Binance Testnet 下一次真實市價單, 證明整條管線接得起來.

**Architecture:** 4 個 agent 是循序呼叫的一般函式 (非獨立行程, 非事件匯流排) , 用 `04_paper_trading/events.py` 定義的型別化事件 (typed events, dataclass) 互相傳遞資料。`run_once.py` 依序呼叫 data_agent → signal_agent → risk_agent → execution_agent, 每步結果記錄成一行 JSON。每個 agent 的決策邏輯是純函數, 用合成 (synthetic) 輸入單元測試; 對外部系統的真實 HTTP 呼叫 (`binance_testnet_client.py`) 不在自動化測試中模擬, 改用一次真實手動執行驗證。

**Tech Stack:** Python 3.11+, pandas, numpy, requests, python-dotenv (皆已在 `requirements.txt`) 。簽名 (signed) 請求用標準庫 `hmac` / `hashlib` / `urllib.parse` 手刻, 不引入 ccxt / python-binance 新依賴。

## Global Constraints

- 不新增 `requirements.txt` 依賴; Binance 簽名請求用標準庫 `hmac`/`hashlib`/`urllib.parse` + 既有的 `requests`。
- 變數名, 函式名, DataFrame 欄位名一律用完整描述性英文, 不縮寫 (CLAUDE.md Naming) 。
- 中文文字一律用英文標點, 且每個標點後面留一個空格, 縮寫在同一檔案內首次出現需標註全稱 (CLAUDE.md Writing) 。
- 訊號 / 指標邏輯 (signal/indicator logic) 一律向量化, 不用 `for` / `if-else`; 執行層 I/O 控制流程 (例如輪詢) 允許用 `for` 迴圈, 與 `engine.py` 的 `apply_trailing_stop_exit` 前例一致。
- `signal_agent.py` 必須直接從 `exp_002_ema_adx/config.py` import `STRATEGY_PARAMS` / `ENGINE_PARAMS`, 不得重複宣告參數字典。
- 本切片範圍: 僅 BTC/USDT, 僅 Binance Testnet, 手動觸發, 僅倉位大小上限風控, 真實下單 (非模擬) 。不做 Alpaca / 排程器 / 完整風控規則 / Telegram 監控 / WebSocket (見設計文件排除範圍) 。
- 每個任務完成後執行 `git add` + `git commit` + `git push` 到目前分支 (CLAUDE.md Git, 不需再次確認) 。
- 純決策邏輯依 TDD (test-driven development, 測試驅動開發) 撰寫; `binance_testnet_client.py` 的 HTTP 呼叫與完整 pipeline 不在自動化測試中模擬, 改用一次真實 Binance Testnet 手動執行驗證 (Task 9) 。

**參照文件:** `docs/superpowers/specs/2026-07-06-phase3-paper-trading-slice1-design.md` (設計規格, 已核准) 。

---

### Task 1: 型別化事件 (events.py) 與測試路徑設定

**Files:**
- Create: `04_paper_trading/events.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_paper_trading_events.py`

**Interfaces:**
- Produces: `SignalEvent(symbol: str, target_position: int, as_of_timestamp: datetime, latest_close_price: float, latest_average_true_range: float)`, `OrderEvent(symbol: str, side: str, quantity: float)`, `RejectionEvent(symbol: str, reason: str)`, `FillEvent(symbol: str, side: str, quantity: float, average_price: float, order_id: str)`, `FailEvent(symbol: str, reason: str, raw_exchange_response: str)` — 全部是 `04_paper_trading/events.py` 的 dataclass, 後續所有任務都會 import 這些型別。

- [ ] **Step 1: 更新 `tests/conftest.py`, 把 `04_paper_trading` 與 `04_paper_trading/agents` 加入模組搜尋路徑**

把現有的 `_research_module_directories` 清單改成:

```python
_research_module_directories = [
    os.path.join(_repository_root, "03_research", "01_indicators"),
    os.path.join(_repository_root, "03_research", "02_strategies"),
    os.path.join(_repository_root, "03_research", "03_backtest"),
    os.path.join(_repository_root, "04_paper_trading"),
    os.path.join(_repository_root, "04_paper_trading", "agents"),
]
```

**Step 2: 寫失敗測試**

Create `tests/test_paper_trading_events.py`:

```python
"""events.py 的型別化事件 (typed events) 冒煙測試 — 確保每個事件的欄位不被意外改名或刪除"""
from datetime import datetime, timezone

from events import FailEvent, FillEvent, OrderEvent, RejectionEvent, SignalEvent


def test_signal_event_holds_all_fields():
    signal_event = SignalEvent(
        symbol="BTCUSDT",
        target_position=1,
        as_of_timestamp=datetime(2026, 7, 6, tzinfo=timezone.utc),
        latest_close_price=50000.0,
        latest_average_true_range=1200.0,
    )
    assert signal_event.symbol == "BTCUSDT"
    assert signal_event.target_position == 1
    assert signal_event.latest_close_price == 50000.0
    assert signal_event.latest_average_true_range == 1200.0


def test_order_event_holds_all_fields():
    order_event = OrderEvent(symbol="BTCUSDT", side="BUY", quantity=0.01)
    assert order_event.side == "BUY"
    assert order_event.quantity == 0.01


def test_rejection_event_holds_all_fields():
    rejection_event = RejectionEvent(symbol="BTCUSDT", reason="超過風控上限")
    assert rejection_event.reason == "超過風控上限"


def test_fill_event_holds_all_fields():
    fill_event = FillEvent(
        symbol="BTCUSDT", side="BUY", quantity=0.01, average_price=50000.0, order_id="123"
    )
    assert fill_event.order_id == "123"


def test_fail_event_holds_all_fields():
    fail_event = FailEvent(symbol="BTCUSDT", reason="狀態不明", raw_exchange_response="{}")
    assert fail_event.reason == "狀態不明"
```

- [ ] **Step 3: 執行測試確認失敗**

Run: `pytest tests/test_paper_trading_events.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'events'`

- [ ] **Step 4: 建立 `04_paper_trading/events.py`**

```python
"""
型別化事件 (typed events) — Slice 1 的 4 個 agent (data / signal / risk / execution) 之間傳遞的資料結構
每個 agent 的決策只依賴這些型別的欄位, 不依賴呼叫者內部細節, 方便個別單元測試
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SignalEvent:
    """signal_agent 的輸出: 這個時間點, 凍結策略認為應該持有的目標倉位"""

    symbol: str
    target_position: int  # 1 = 多單(long) , 0 = 空手(flat)
    as_of_timestamp: datetime
    latest_close_price: float
    latest_average_true_range: float


@dataclass
class OrderEvent:
    """risk_agent 核准後的下單指令"""

    symbol: str
    side: str  # "BUY" 或 "SELL"
    quantity: float


@dataclass
class RejectionEvent:
    """risk_agent 認為該交易, 但被風控規則擋下"""

    symbol: str
    reason: str


@dataclass
class FillEvent:
    """execution_agent 確認成交"""

    symbol: str
    side: str
    quantity: float
    average_price: float
    order_id: str


@dataclass
class FailEvent:
    """execution_agent 下單或確認失敗 (含狀態不明) """

    symbol: str
    reason: str
    raw_exchange_response: str
```

- [ ] **Step 5: 執行測試確認通過**

Run: `pytest tests/test_paper_trading_events.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py 04_paper_trading/events.py tests/test_paper_trading_events.py
git commit -m "feat: add typed events for paper trading pipeline"
git push
```

---

### Task 2: 重構 binance_fetcher.py, 抽出可重用的請求與解析函式

**Files:**
- Modify: `02_data/fetchers/binance_fetcher.py` (完整重寫, 行為對 `fetch_full_history_klines` 與 `save_to_cache` 保持不變)
- Test: `tests/test_binance_fetcher_parsing.py`

**Interfaces:**
- Produces: `request_klines_batch(symbol: str, interval: str, limit: int, start_time_milliseconds: int | None = None) -> list`, `parse_klines_to_ohlcv_dataframe(klines_batch: list) -> pd.DataFrame` (輸出欄位含 `close_time`, 供 `drop_unclosed_last_candle` 判斷) , `drop_unclosed_last_candle(ohlcv_dataframe: pd.DataFrame) -> pd.DataFrame` (輸出欄位為 `open_time, open, high, low, close, volume`, 已移除 `close_time`) — Task 3 的 `data_agent.py` 會直接 import 這三個函式。
- Consumes: 無 (只依賴 `requests`, `pandas`) 。

此任務需要先確認重構「行為不變」, 採用「先驗證舊行為, 再重構, 再驗證新行為」的手法, 而非標準 TDD 紅綠燈 (因為這是重構既有程式碼, 不是新增行為) 。

- [ ] **Step 1: 記錄重構前的基準輸出 (供之後比對, 不寫入版本控制) **

只存 `head(3)`(歷史最早幾筆, 不受「現在幾點執行」影響, 適合逐字比對) ; 根數與 `tail(3)` 會隨時間持續變動, 不適合拿來判斷重構是否改變行為, 故不用於比對:

```bash
cd /home/ubuntu/jerome/quant-trading-system
python3 -c "
import sys
sys.path.insert(0, '02_data/fetchers')
from binance_fetcher import fetch_full_history_klines
df = fetch_full_history_klines('BTCUSDT', '1d')
print(df.head(3).to_string())
" > /tmp/binance_fetcher_before_head.txt
cat /tmp/binance_fetcher_before_head.txt
```
Expected: 印出最早 3 根 K 線, 記下這份輸出供 Step 5 比對。

- [ ] **Step 2: 寫純解析邏輯的失敗測試 (不打真實網路請求) **

Create `tests/test_binance_fetcher_parsing.py`:

```python
"""binance_fetcher.py 純解析邏輯的單元測試 — 不打真實網路請求, 用手造的假 K 線陣列驗證"""
import pandas as pd

from binance_fetcher import drop_unclosed_last_candle, parse_klines_to_ohlcv_dataframe


def _make_raw_kline(open_time_ms, close_time_ms, close_price="100.0"):
    """造一根 Binance 格式的原始 K 線陣列 (12 個無名欄位, 順序見 binance_fetcher.KLINE_COLUMNS) """
    return [
        open_time_ms, "100.0", "101.0", "99.0", close_price, "10.0",
        close_time_ms, "1000.0", 5, "5.0", "500.0", "0",
    ]


def test_parse_klines_to_ohlcv_dataframe_maps_core_columns():
    raw_klines = [
        _make_raw_kline(0, 86_399_999, "100.0"),
        _make_raw_kline(86_400_000, 172_799_999, "105.0"),
    ]
    ohlcv_dataframe = parse_klines_to_ohlcv_dataframe(raw_klines)
    assert list(ohlcv_dataframe["close"]) == [100.0, 105.0]
    assert ohlcv_dataframe["open_time"].iloc[0] == pd.Timestamp("1970-01-01")


def test_drop_unclosed_last_candle_removes_future_candle():
    far_future_open_ms = int(pd.Timestamp("2999-01-01").timestamp() * 1000)
    far_future_close_ms = far_future_open_ms + 86_399_999
    raw_klines = [
        _make_raw_kline(0, 86_399_999, "100.0"),
        _make_raw_kline(86_400_000, far_future_close_ms, "999.0"),
    ]
    ohlcv_dataframe = parse_klines_to_ohlcv_dataframe(raw_klines)
    trimmed_dataframe = drop_unclosed_last_candle(ohlcv_dataframe)
    assert len(trimmed_dataframe) == 1
    assert trimmed_dataframe["close"].iloc[0] == 100.0
    assert "close_time" not in trimmed_dataframe.columns


def test_drop_unclosed_last_candle_keeps_all_when_already_closed():
    raw_klines = [_make_raw_kline(0, 86_399_999, "100.0")]
    ohlcv_dataframe = parse_klines_to_ohlcv_dataframe(raw_klines)
    trimmed_dataframe = drop_unclosed_last_candle(ohlcv_dataframe)
    assert len(trimmed_dataframe) == 1
```

- [ ] **Step 3: 執行測試確認失敗**

Run: `pytest tests/test_binance_fetcher_parsing.py -v`
Expected: FAIL, `ImportError: cannot import name 'parse_klines_to_ohlcv_dataframe'`

- [ ] **Step 4: 重寫 `02_data/fetchers/binance_fetcher.py`**

完整取代檔案內容為:

```python
"""
Binance 歷史 K 線抓取器 — 從 Binance 公開行情 API 分頁抓取指定交易對的完整歷史日線
公開行情端點不需要 API Key. Binance 單次最多回傳 1000 根 K 線, 需用 startTime 分頁往後累積,
直到抓到最新一根. 抓下來的數據存到本地 cache(被 gitignore) , 供研究層重複讀取, 不必每次重打 API
本檔的請求與解析函式 (request_klines_batch, parse_klines_to_ohlcv_dataframe, drop_unclosed_last_candle)
也被 04_paper_trading/agents/data_agent.py 重用, 供即時抓取最新 K 線, 兩處共用同一段已測試邏輯
"""

import os
import time

import pandas as pd
import requests

BINANCE_KLINES_ENDPOINT = "https://api.binance.com/api/v3/klines"
# 單次請求上限, Binance 官方硬性限制為 1000 根
MAX_KLINES_PER_REQUEST = 1000

# Binance 回傳的每根 K 線是無欄位名的陣列, 按官方文件順序對應成有意義的欄位名
KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
]
PRICE_AND_VOLUME_COLUMNS = ["open", "high", "low", "close", "volume"]


def request_klines_batch(
    symbol: str, interval: str, limit: int, start_time_milliseconds: int | None = None
) -> list:
    """
    打一次 Binance 公開 K 線端點, 回傳原始 (未解析) 的 K 線陣列列表
    參數 start_time_milliseconds 為 None 時, Binance 回傳「最新」的 limit 根 K 線 (不分頁, 供即時抓取用)
    給定 start_time_milliseconds 時, 回傳從該時間點開始的 limit 根 (供歷史分頁抓取用)
    """
    request_parameters = {"symbol": symbol, "interval": interval, "limit": limit}
    if start_time_milliseconds is not None:
        request_parameters["startTime"] = start_time_milliseconds
    response = requests.get(BINANCE_KLINES_ENDPOINT, params=request_parameters, timeout=30)
    response.raise_for_status()
    return response.json()


def parse_klines_to_ohlcv_dataframe(klines_batch: list) -> pd.DataFrame:
    """
    把 Binance 原始 K 線陣列列表解析成核心 OHLCV(開高低收量) 欄位 + close_time 的 DataFrame, 時間升冪排列
    保留 close_time 供 drop_unclosed_last_candle 判斷最後一根是否已收盤, 該函式回傳前會將其移除
    """
    kline_dataframe = pd.DataFrame(klines_batch, columns=KLINE_COLUMNS)
    kline_dataframe["open_time"] = pd.to_datetime(kline_dataframe["open_time"], unit="ms")
    kline_dataframe[PRICE_AND_VOLUME_COLUMNS] = kline_dataframe[
        PRICE_AND_VOLUME_COLUMNS
    ].astype(float)
    kline_dataframe["close_time"] = pd.to_datetime(kline_dataframe["close_time"], unit="ms")
    return kline_dataframe[
        ["open_time", "open", "high", "low", "close", "volume", "close_time"]
    ].copy()


def drop_unclosed_last_candle(ohlcv_dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    最後一根 K 線通常尚未收盤(仍在跳動) , 為避免用到不完整數據, 若尚未收盤則移除
    回傳前移除 close_time 輔助欄位, 只留核心 OHLCV 欄位, 並重設索引
    """
    last_close_time = ohlcv_dataframe["close_time"].iloc[-1]
    current_utc_time = pd.Timestamp.now("UTC").tz_localize(None)
    if last_close_time > current_utc_time:
        ohlcv_dataframe = ohlcv_dataframe.iloc[:-1]
    return ohlcv_dataframe.drop(columns=["close_time"]).reset_index(drop=True)


def fetch_full_history_klines(
    symbol: str, interval: str = "1d", request_pause_seconds: float = 0.2
) -> pd.DataFrame:
    """
    分頁抓取某交易對從上市至今的完整歷史 K 線
    參數 symbol: 交易對代號, 例如 "BTCUSDT"
    參數 interval: K 線週期, 例如 "1d"(日線) , "4h"(4 小時線)
    參數 request_pause_seconds: 每次請求之間的暫停, 禮貌性避免觸發 Binance 速率限制
    回傳只含核心 OHLCV 欄位的 DataFrame, 時間升冪排列, 已去除最後一根未收盤 K 線
    """
    accumulated_rows = []
    # startTime 設為 0, Binance 會自動從該交易對真正上市的第一根 K 線開始回傳
    next_start_time_milliseconds = 0

    while True:
        klines_batch = request_klines_batch(
            symbol, interval, MAX_KLINES_PER_REQUEST, next_start_time_milliseconds
        )
        if not klines_batch:
            break

        accumulated_rows.extend(klines_batch)
        # 下一頁從這一頁最後一根 K 線的開盤時間 + 1 毫秒開始, 避免重複抓到同一根
        last_open_time_milliseconds = klines_batch[-1][0]
        next_start_time_milliseconds = last_open_time_milliseconds + 1

        # 回傳數量不足一整頁, 代表已經抓到最新一根, 結束分頁
        if len(klines_batch) < MAX_KLINES_PER_REQUEST:
            break
        time.sleep(request_pause_seconds)

    ohlcv_dataframe = parse_klines_to_ohlcv_dataframe(accumulated_rows)
    return drop_unclosed_last_candle(ohlcv_dataframe)


def save_to_cache(ohlcv_dataframe: pd.DataFrame, cache_file_name: str) -> str:
    """把抓取結果存到 02_data/cache/ 目錄, 回傳實際存檔路徑; cache 目錄由 gitignore 排除"""
    cache_directory = os.path.join(os.path.dirname(__file__), "..", "cache")
    os.makedirs(cache_directory, exist_ok=True)
    cache_file_path = os.path.join(cache_directory, cache_file_name)
    ohlcv_dataframe.to_csv(cache_file_path, index=False)
    return cache_file_path


if __name__ == "__main__":
    # 直接執行時, 抓取研究層 Round 1 基準需要的加密貨幣日線: BTC/USDT 與 ETH/USDT
    for trading_symbol, output_file_name in [
        ("BTCUSDT", "btc_usdt_1d.csv"),
        ("ETHUSDT", "eth_usdt_1d.csv"),
    ]:
        history_dataframe = fetch_full_history_klines(trading_symbol, "1d")
        saved_path = save_to_cache(history_dataframe, output_file_name)
        print(
            f"{trading_symbol}: 抓取 {len(history_dataframe)} 根日線 "
            f"({history_dataframe['open_time'].iloc[0].date()} 至 "
            f"{history_dataframe['open_time'].iloc[-1].date()}) , 已存到 {saved_path}"
        )
```

- [ ] **Step 5: 執行新測試確認通過, 並手動比對重構前後行為一致**

Run: `pytest tests/test_binance_fetcher_parsing.py -v`
Expected: 3 passed

Run (只比對 `head(3)`, 這 3 筆是 2017 年最早期的歷史數據, 不受執行時間影響, 逐字相同才代表解析邏輯行為不變):
```bash
cd /home/ubuntu/jerome/quant-trading-system
python3 -c "
import sys
sys.path.insert(0, '02_data/fetchers')
from binance_fetcher import fetch_full_history_klines
df = fetch_full_history_klines('BTCUSDT', '1d')
print(df.head(3).to_string())
" > /tmp/binance_fetcher_after_head.txt
diff /tmp/binance_fetcher_before_head.txt /tmp/binance_fetcher_after_head.txt && echo "HEAD(3) 完全相同, 解析邏輯行為不變"
```
Expected: `diff` 無輸出 (兩份檔案完全相同) , 印出 `HEAD(3) 完全相同, 解析邏輯行為不變`。

- [ ] **Step 6: 執行完整測試套件確認沒有連帶破壞既有測試**

Run: `pytest tests/ -v`
Expected: 全部通過 (含既有的 test_indicators.py, test_backtest.py, test_engine_invariants.py, test_trailing_stop.py, test_risk.py)

- [ ] **Step 7: Commit**

```bash
git add 02_data/fetchers/binance_fetcher.py tests/test_binance_fetcher_parsing.py
git commit -m "refactor: extract reusable request/parse functions from binance_fetcher"
git push
```

---

### Task 3: data_agent.py — 拉取最新 K 線

**Files:**
- Create: `04_paper_trading/agents/data_agent.py`
- Test: `tests/test_paper_trading_data_agent.py`

**Interfaces:**
- Consumes: `binance_fetcher.request_klines_batch`, `parse_klines_to_ohlcv_dataframe`, `drop_unclosed_last_candle` (Task 2) 。
- Produces: `fetch_latest_candles(symbol: str, interval: str = "1d", lookback_bars: int = 100) -> pd.DataFrame` — Task 8 的 `run_once.py` 會呼叫 `data_agent.fetch_latest_candles(symbol)`。

- [ ] **Step 1: 寫失敗測試**

Create `tests/test_paper_trading_data_agent.py`:

```python
"""data_agent.fetch_latest_candles 的單元測試 — monkeypatch 掉真實網路請求, 只測試組裝與長度檢查邏輯"""
import pandas as pd
import pytest

import data_agent


def _make_raw_kline(open_time_ms, close_time_ms):
    return [
        open_time_ms, "100.0", "101.0", "99.0", "100.0", "10.0",
        close_time_ms, "1000.0", 5, "5.0", "500.0", "0",
    ]


def test_fetch_latest_candles_returns_requested_length(monkeypatch):
    interval_milliseconds = 86_400_000
    # 建構 11 根日線: 前 10 根已收盤(收盤時間在過去) , 最後一根尚未收盤(收盤時間在未來)
    now_milliseconds = int(pd.Timestamp.now("UTC").timestamp() * 1000)
    first_open_milliseconds = now_milliseconds - 10 * interval_milliseconds
    raw_klines = []
    for index in range(11):
        open_milliseconds = first_open_milliseconds + index * interval_milliseconds
        close_milliseconds = open_milliseconds + interval_milliseconds - 1
        raw_klines.append(_make_raw_kline(open_milliseconds, close_milliseconds))
    monkeypatch.setattr(
        data_agent, "request_klines_batch", lambda symbol, interval, limit: raw_klines
    )

    ohlcv_dataframe = data_agent.fetch_latest_candles("BTCUSDT", lookback_bars=10)

    assert len(ohlcv_dataframe) == 10
    assert list(ohlcv_dataframe.columns) == [
        "open_time", "open", "high", "low", "close", "volume",
    ]


def test_fetch_latest_candles_raises_when_insufficient_bars(monkeypatch):
    interval_milliseconds = 86_400_000
    raw_klines = [
        _make_raw_kline(day * interval_milliseconds, day * interval_milliseconds + interval_milliseconds - 1)
        for day in range(5)
    ]
    monkeypatch.setattr(
        data_agent, "request_klines_batch", lambda symbol, interval, limit: raw_klines
    )

    with pytest.raises(ValueError, match="少於暖身所需"):
        data_agent.fetch_latest_candles("BTCUSDT", lookback_bars=10)
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_paper_trading_data_agent.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'data_agent'`

- [ ] **Step 3: 建立 `04_paper_trading/agents/data_agent.py`**

```python
"""
Data agent — 拉取最新 K 線, 供 signal_agent 產生即時信號用
重用 02_data/fetchers/binance_fetcher.py 的請求與解析邏輯 (request_klines_batch,
parse_klines_to_ohlcv_dataframe, drop_unclosed_last_candle) , 不重寫一份, 讓歷史抓取與即時抓取
共用同一段已測試過的程式碼路徑
"""
import os
import sys

import pandas as pd

_agents_directory = os.path.dirname(os.path.abspath(__file__))
_paper_trading_directory = os.path.dirname(_agents_directory)
_repository_root = os.path.dirname(_paper_trading_directory)
sys.path.insert(0, os.path.join(_repository_root, "02_data", "fetchers"))
from binance_fetcher import (  # noqa: E402
    drop_unclosed_last_candle,
    parse_klines_to_ohlcv_dataframe,
    request_klines_batch,
)

# 暖身期保守值: exp_002 的 slow_span=26 / adx_period=14 皆為威爾德式平滑(Wilder smoothing) ,
# 對更早數據的權重會隨窗口拉長而指數衰減但不會歸零; 100 根後殘餘權重已降到千分之一以下,
# 比嚴格暖身期(約 26-40 根) 更保守, 讓即時計算的指標值更貼近回測用全歷史算出的版本
DEFAULT_LOOKBACK_BARS = 100


def fetch_latest_candles(
    symbol: str, interval: str = "1d", lookback_bars: int = DEFAULT_LOOKBACK_BARS
) -> pd.DataFrame:
    """
    拉取最近 lookback_bars 根已收盤 K 線, 足夠 exp_002 策略指標暖身
    回傳按時間升冪排列, 只含核心 OHLCV(開高低收量) 欄位的 DataFrame
    拋出 ValueError: 若已收盤根數少於 lookback_bars(數據不足, 不該在殘缺窗口上硬算指標)
    """
    # 多拉一根: 最後一根若尚未收盤會被丟棄, 需要多要一根才能保證丟棄後仍有 lookback_bars 根
    raw_klines = request_klines_batch(symbol, interval, limit=lookback_bars + 1)
    ohlcv_dataframe = parse_klines_to_ohlcv_dataframe(raw_klines)
    ohlcv_dataframe = drop_unclosed_last_candle(ohlcv_dataframe)
    if len(ohlcv_dataframe) < lookback_bars:
        raise ValueError(
            f"{symbol} 只抓到 {len(ohlcv_dataframe)} 根已收盤 K 線, "
            f"少於暖身所需的 {lookback_bars} 根"
        )
    return ohlcv_dataframe
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest tests/test_paper_trading_data_agent.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add 04_paper_trading/agents/data_agent.py tests/test_paper_trading_data_agent.py
git commit -m "feat: add data_agent for fetching latest candles"
git push
```

---

### Task 4: binance_testnet_client.py — 簽名 REST 客戶端

**Files:**
- Create: `04_paper_trading/binance_testnet_client.py`
- Test: `tests/test_binance_testnet_client_rounding.py`

**Interfaces:**
- Produces: `get_account_balances() -> dict`, `get_symbol_filters(symbol: str) -> dict` (含 `step_size`, `min_notional`) , `place_market_order(symbol: str, side: str, quantity: float) -> tuple[int, dict]`, `get_order_status(symbol: str, order_id: int) -> tuple[int, dict]`, `round_quantity_to_step_size(quantity: float, step_size: float | None) -> float` — Task 7 (`execution_agent.py`) 與 Task 8 (`run_once.py`) 會 import 這些函式。

只有 `round_quantity_to_step_size` 是純函數, 這裡走完整 TDD; 其餘函式是 I/O 邊界, 依設計文件不在自動化測試中模擬, 但仍須寫出完整程式碼 (無真實憑證時, 手動執行會因缺憑證報錯, 這是預期行為, 見 Task 9) 。

- [ ] **Step 1: 寫純函數的失敗測試**

Create `tests/test_binance_testnet_client_rounding.py`:

```python
"""binance_testnet_client.round_quantity_to_step_size 的單元測試 — 純函數, 不打真實網路請求"""
import pytest

from binance_testnet_client import round_quantity_to_step_size


def test_round_quantity_to_step_size_rounds_down_to_nearest_step():
    assert round_quantity_to_step_size(0.123456, 0.0001) == pytest.approx(0.1234)


def test_round_quantity_to_step_size_exact_multiple_unchanged():
    assert round_quantity_to_step_size(0.005, 0.001) == pytest.approx(0.005)


def test_round_quantity_to_step_size_none_step_size_returns_original_quantity():
    assert round_quantity_to_step_size(0.123456, None) == 0.123456
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_binance_testnet_client_rounding.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'binance_testnet_client'`

- [ ] **Step 3: 建立 `04_paper_trading/binance_testnet_client.py`**

```python
"""
Binance Testnet 交易客戶端 — 簽名 (signed) REST 呼叫, 用於紙上交易 (paper trading) 查詢帳戶與下單
與 02_data/fetchers/binance_fetcher.py 的公開行情端點不同, 這裡的端點需要 API Key 簽名驗證,
使用 HMAC(Hash-based Message Authentication Code) -SHA256 手動簽名, 不引入 python-binance/ccxt,
延續本專案偏好手刻 REST 呼叫, 依賴透明的風格(參見 factor_regression.py 手刻 OLS 迴歸的選擇)
"""
import hashlib
import hmac
import math
import os
import time
import urllib.parse

import requests
from dotenv import load_dotenv

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
_repository_root = os.path.dirname(_paper_trading_directory)
load_dotenv(os.path.join(_repository_root, ".env"))

BASE_URL = "https://testnet.binance.vision"
REQUEST_TIMEOUT_SECONDS = 30


def _get_credentials() -> tuple[str, str]:
    """從 .env 讀取 Binance Testnet 憑證, 缺少時直接報錯提示先設定"""
    api_key = os.getenv("BINANCE_TESTNET_API_KEY")
    api_secret = os.getenv("BINANCE_TESTNET_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError(
            "缺少 Binance Testnet 憑證, 請先在 .env 填入 BINANCE_TESTNET_API_KEY 與 BINANCE_TESTNET_SECRET"
        )
    return api_key, api_secret


def _signed_request(http_method: str, path: str, params: dict) -> tuple[int, dict]:
    """
    對需要驗證的端點發出簽名請求, 回傳 (HTTP 狀態碼, 解析後的 JSON)
    刻意不對非 2xx 狀態呼叫 raise_for_status, 讓呼叫端可以檢查交易所回傳的錯誤內容
    (例如 LOT_SIZE / MIN_NOTIONAL 過濾失敗) , 只有真正的網路層例外才會往外拋
    """
    api_key, api_secret = _get_credentials()
    signed_parameters = dict(params)
    signed_parameters["timestamp"] = int(time.time() * 1000)
    query_string = urllib.parse.urlencode(signed_parameters)
    signature = hmac.new(
        api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    query_string_with_signature = f"{query_string}&signature={signature}"

    url = f"{BASE_URL}{path}?{query_string_with_signature}"
    response = requests.request(
        http_method,
        url,
        headers={"X-MBX-APIKEY": api_key},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return response.status_code, response.json()


def get_account_balances() -> dict:
    """查詢帳戶餘額, 回傳 {資產代號: 可用餘額} 字典, 只含餘額不為零的資產"""
    status_code, response_body = _signed_request("GET", "/api/v3/account", {})
    if status_code != 200:
        raise RuntimeError(f"查詢帳戶餘額失敗: HTTP {status_code}, {response_body}")
    return {
        balance["asset"]: float(balance["free"])
        for balance in response_body["balances"]
        if float(balance["free"]) > 0
    }


def get_symbol_filters(symbol: str) -> dict:
    """
    查詢交易對的下單規則, 回傳 {"step_size": 數量最小級距, "min_notional": 最小下單金額}
    這是公開端點, 不需簽名; Binance 不同時期用 MIN_NOTIONAL 或 NOTIONAL 命名同一種過濾規則, 兩者都嘗試讀取
    """
    response = requests.get(
        f"{BASE_URL}/api/v3/exchangeInfo",
        params={"symbol": symbol},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    symbol_info = response.json()["symbols"][0]
    step_size = None
    min_notional = None
    for filter_definition in symbol_info["filters"]:
        if filter_definition["filterType"] == "LOT_SIZE":
            step_size = float(filter_definition["stepSize"])
        elif filter_definition["filterType"] in ("MIN_NOTIONAL", "NOTIONAL"):
            min_notional = float(
                filter_definition.get("minNotional", filter_definition.get("notional"))
            )
    return {"step_size": step_size, "min_notional": min_notional}


def round_quantity_to_step_size(quantity: float, step_size: float | None) -> float:
    """
    把下單數量向下裁到 step_size 的整數倍, 避免觸發 Binance 的 LOT_SIZE 過濾規則
    純函數, 不牽涉網路請求, 可獨立單元測試
    """
    if step_size is None or step_size <= 0:
        return quantity
    number_of_steps = math.floor(quantity / step_size)
    return number_of_steps * step_size


def place_market_order(symbol: str, side: str, quantity: float) -> tuple[int, dict]:
    """
    下市價單, 參數 side 為 "BUY" 或 "SELL"
    回傳 (HTTP 狀態碼, 交易所回應 JSON) , 不拋例外, 由呼叫端(execution_agent) 判斷成敗
    """
    return _signed_request(
        "POST",
        "/api/v3/order",
        {"symbol": symbol, "side": side, "type": "MARKET", "quantity": quantity},
    )


def get_order_status(symbol: str, order_id: int) -> tuple[int, dict]:
    """查詢訂單目前狀態, 回傳 (HTTP 狀態碼, 交易所回應 JSON) """
    return _signed_request("GET", "/api/v3/order", {"symbol": symbol, "orderId": order_id})
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest tests/test_binance_testnet_client_rounding.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add 04_paper_trading/binance_testnet_client.py tests/test_binance_testnet_client_rounding.py
git commit -m "feat: add signed Binance Testnet REST client"
git push
```

---

### Task 5: signal_agent.py — 用凍結參數決定目標倉位

**Files:**
- Create: `04_paper_trading/agents/signal_agent.py`
- Test: `tests/test_paper_trading_signal_agent.py`

**Interfaces:**
- Consumes: `events.SignalEvent` (Task 1) ; `exp_002_ema_adx/config.py` 的 `STRATEGY_PARAMS`, `ENGINE_PARAMS`; `trend_following.TrendFollowingStrategy`; `volatility.average_true_range`。
- Produces: `decide(ohlcv_dataframe: pd.DataFrame, symbol: str) -> SignalEvent`, 模組常數 `FROZEN_STRATEGY_PARAMETERS: dict`, `FROZEN_ENGINE_PARAMETERS: dict` — Task 6 的測試與 Task 8 的 `run_once.py` 都會用到 `FROZEN_ENGINE_PARAMETERS`。

- [ ] **Step 1: 寫失敗測試**

Create `tests/test_paper_trading_signal_agent.py`:

```python
"""signal_agent.decide 的單元測試 — 用手造的確定性價格序列驗證多單/空手判斷與事件欄位"""
import numpy as np
import pandas as pd

import signal_agent


def _make_ohlcv(closes) -> pd.DataFrame:
    """比照 tests/test_trailing_stop.py 的手法: 由收盤價序列造 OHLCV, high/low 取 ±1 固定區間"""
    close_price = pd.Series(closes, dtype=float)
    return pd.DataFrame(
        {
            "open_time": pd.date_range("2020-01-01", periods=len(close_price), freq="D"),
            "open": close_price,
            "high": close_price + 1.0,
            "low": close_price - 1.0,
            "close": close_price,
            "volume": pd.Series(np.full(len(close_price), 1000.0)),
        }
    )


def test_decide_reports_long_when_strong_uptrend():
    # 持續上漲 120 天, 快線在慢線之上且趨勢夠強(ADX 應高於凍結門檻 25) , 目標倉位應為多單(1)
    closes = np.linspace(100, 400, 120)
    ohlcv_dataframe = _make_ohlcv(closes)

    signal_event = signal_agent.decide(ohlcv_dataframe, "BTCUSDT")

    assert signal_event.symbol == "BTCUSDT"
    assert signal_event.target_position == 1
    assert signal_event.latest_close_price == closes[-1]
    assert signal_event.latest_average_true_range > 0
    assert signal_event.as_of_timestamp.date() == ohlcv_dataframe["open_time"].iloc[-1].date()


def test_decide_reports_flat_when_price_is_flat():
    # 完全走平 120 天, 快慢線相等無交叉, 目標倉位應為空手(0) , 與 ADX 高低無關
    closes = np.full(120, 100.0)
    ohlcv_dataframe = _make_ohlcv(closes)

    signal_event = signal_agent.decide(ohlcv_dataframe, "BTCUSDT")

    assert signal_event.target_position == 0
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_paper_trading_signal_agent.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'signal_agent'`

- [ ] **Step 3: 建立 `04_paper_trading/agents/signal_agent.py`**

```python
"""
Signal agent — 用 exp_002 凍結參數跑趨勢跟蹤(trend following) 策略, 決定「現在」該有的目標倉位
直接從 exp_002_ema_adx/config.py import 凍結參數, 不重複宣告字典, 確保紙上交易與回測參數永遠一致
"""
import os
import sys
from datetime import timezone

import pandas as pd

_agents_directory = os.path.dirname(os.path.abspath(__file__))
_paper_trading_directory = os.path.dirname(_agents_directory)
_repository_root = os.path.dirname(_paper_trading_directory)
for _module_subdirectory in ["01_indicators", "02_strategies", "03_backtest"]:
    sys.path.insert(0, os.path.join(_repository_root, "03_research", _module_subdirectory))
sys.path.insert(
    0, os.path.join(_repository_root, "03_research", "04_experiments", "exp_002_ema_adx")
)
sys.path.insert(0, _paper_trading_directory)

from config import ENGINE_PARAMS, STRATEGY_PARAMS  # noqa: E402
from trend_following import TrendFollowingStrategy  # noqa: E402
from volatility import average_true_range  # noqa: E402

from events import SignalEvent  # noqa: E402

# 重新匯出凍結參數, 讓 run_once.py 與測試不用各自再走一次 exp_002 config.py 的路徑手續
FROZEN_STRATEGY_PARAMETERS = STRATEGY_PARAMS
FROZEN_ENGINE_PARAMETERS = ENGINE_PARAMS

_FROZEN_STRATEGY = TrendFollowingStrategy(**STRATEGY_PARAMS)


def decide(ohlcv_dataframe: pd.DataFrame, symbol: str) -> SignalEvent:
    """
    對輸入的 OHLCV(開高低收量) 數據跑凍結的 exp_002 策略, 取最後一列的目標倉位當作「現在」的決策
    參數 ohlcv_dataframe: 至少需涵蓋策略暖身期, 由 data_agent.fetch_latest_candles 提供
    回傳 SignalEvent, target_position 為 0(空手) 或 1(多單)
    """
    target_position_series = _FROZEN_STRATEGY.generate_signals(ohlcv_dataframe)
    average_true_range_series = average_true_range(
        ohlcv_dataframe["high"],
        ohlcv_dataframe["low"],
        ohlcv_dataframe["close"],
        FROZEN_ENGINE_PARAMETERS["atr_period"],
    )
    latest_row = ohlcv_dataframe.iloc[-1]
    return SignalEvent(
        symbol=symbol,
        target_position=int(target_position_series.iloc[-1]),
        as_of_timestamp=latest_row["open_time"].to_pydatetime().replace(tzinfo=timezone.utc),
        latest_close_price=float(latest_row["close"]),
        latest_average_true_range=float(average_true_range_series.iloc[-1]),
    )
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest tests/test_paper_trading_signal_agent.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add 04_paper_trading/agents/signal_agent.py tests/test_paper_trading_signal_agent.py
git commit -m "feat: add signal_agent running frozen exp_002 strategy"
git push
```

---

### Task 6: risk_agent.py — 比對倉位, 套用倉位大小上限

**Files:**
- Create: `04_paper_trading/agents/risk_agent.py`
- Test: `tests/test_paper_trading_risk_agent.py`

**Interfaces:**
- Consumes: `events.SignalEvent`, `OrderEvent`, `RejectionEvent` (Task 1) ; `engine.compute_position_fraction` (既有函式, 簽名: `compute_position_fraction(close_price: pd.Series, average_true_range_series: pd.Series, risk_per_trade_percentage: float, atr_stop_multiplier: float, max_position_fraction: float) -> pd.Series`) 。
- Produces: `determine_current_position(base_asset_balance: float, base_asset_price_in_usdt: float) -> int`, `compute_buy_quantity(account_equity_usdt: float, close_price: float, average_true_range: float, risk_per_trade_percentage: float, atr_stop_multiplier: float, max_position_fraction: float) -> float`, `review(signal_event: SignalEvent, current_base_asset_balance: float, account_equity_usdt: float, engine_parameters: dict) -> OrderEvent | RejectionEvent | None` — Task 8 的 `run_once.py` 會呼叫 `risk_agent.review(...)`。

- [ ] **Step 1: 寫失敗測試**

Create `tests/test_paper_trading_risk_agent.py`:

```python
"""risk_agent 的單元測試 — 涵蓋三種結果分支: 無動作, 核准下單(買/賣) , 風控擋下"""
from datetime import datetime, timezone

import pytest

import risk_agent
from events import OrderEvent, RejectionEvent, SignalEvent

ENGINE_PARAMETERS = {
    "initial_capital": 10_000.0,
    "risk_per_trade_percentage": 0.01,
    "atr_stop_multiplier": 2.0,
    "max_position_fraction": 1.0,
}


def _make_signal_event(
    target_position: int, close_price: float = 50_000.0, average_true_range: float = 1_000.0
) -> SignalEvent:
    return SignalEvent(
        symbol="BTCUSDT",
        target_position=target_position,
        as_of_timestamp=datetime(2026, 7, 6, tzinfo=timezone.utc),
        latest_close_price=close_price,
        latest_average_true_range=average_true_range,
    )


def test_determine_current_position_flat_when_below_dust_threshold():
    assert risk_agent.determine_current_position(0.0001, 50_000.0) == 0  # 市值 5 USDT, 低於 10 門檻


def test_determine_current_position_long_when_above_dust_threshold():
    assert risk_agent.determine_current_position(0.001, 50_000.0) == 1  # 市值 50 USDT, 高於 10 門檻


def test_review_returns_none_when_target_matches_current():
    signal_event = _make_signal_event(target_position=0)

    result = risk_agent.review(signal_event, 0.0, 10_000.0, ENGINE_PARAMETERS)

    assert result is None


def test_review_returns_sell_order_closing_full_position():
    signal_event = _make_signal_event(target_position=0)

    result = risk_agent.review(signal_event, 0.05, 10_000.0, ENGINE_PARAMETERS)

    assert isinstance(result, OrderEvent)
    assert result.side == "SELL"
    assert result.quantity == 0.05


def test_review_returns_buy_order_within_risk_cap():
    signal_event = _make_signal_event(target_position=1, close_price=50_000.0, average_true_range=1_000.0)

    result = risk_agent.review(signal_event, 0.0, 10_000.0, ENGINE_PARAMETERS)

    assert isinstance(result, OrderEvent)
    assert result.side == "BUY"
    # 佔比 = 1% * 50000 / (2 * 1000) = 0.25, 部位金額 = 10000 * 0.25 = 2500 USDT, 數量 = 2500/50000 = 0.05
    assert result.quantity == pytest.approx(0.05)


def test_review_rejects_buy_when_notional_exceeds_cap():
    # 用比較小的 initial_capital 讓風控上限低於算出的買進金額, 觸發 RejectionEvent
    signal_event = _make_signal_event(target_position=1, close_price=50_000.0, average_true_range=1_000.0)
    small_cap_engine_parameters = dict(ENGINE_PARAMETERS, initial_capital=1_000.0)

    result = risk_agent.review(signal_event, 0.0, 10_000.0, small_cap_engine_parameters)

    assert isinstance(result, RejectionEvent)
    assert "超過風控上限" in result.reason
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_paper_trading_risk_agent.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'risk_agent'`

- [ ] **Step 3: 建立 `04_paper_trading/agents/risk_agent.py`**

```python
"""
Risk agent — 比對策略目標倉位與交易所目前實際倉位, 決定要不要下單, 下多少
本切片(Slice 1) 只做最小風控: 買進方向的名目金額(notional) 上限檢查;
完整風控規則(每日熔斷, 相關性限制, 最大同時持倉數等) 留給後續切片, 見設計文件排除範圍
"""
import os
import sys

import pandas as pd

_agents_directory = os.path.dirname(os.path.abspath(__file__))
_paper_trading_directory = os.path.dirname(_agents_directory)
_repository_root = os.path.dirname(_paper_trading_directory)
sys.path.insert(0, os.path.join(_repository_root, "03_research", "03_backtest"))
sys.path.insert(0, _paper_trading_directory)

from engine import compute_position_fraction  # noqa: E402

from events import OrderEvent, RejectionEvent, SignalEvent  # noqa: E402

# BTC 市值低於這個 USDT 門檻視為粉塵(dust) , 不算真的持有部位
DUST_VALUE_THRESHOLD_USDT = 10.0


def determine_current_position(
    base_asset_balance: float, base_asset_price_in_usdt: float
) -> int:
    """把交易所回傳的實際餘額換算成 0(空手) 或 1(多單) , 市值低於粉塵門檻視為空手"""
    return int(base_asset_balance * base_asset_price_in_usdt >= DUST_VALUE_THRESHOLD_USDT)


def compute_buy_quantity(
    account_equity_usdt: float,
    close_price: float,
    average_true_range: float,
    risk_per_trade_percentage: float,
    atr_stop_multiplier: float,
    max_position_fraction: float,
) -> float:
    """用引擎既有的固定風險倉位公式算出買進數量(單位: 標的資產, 例如 BTC) , 與回測時的進場邏輯一致"""
    position_fraction_series = compute_position_fraction(
        pd.Series([close_price]),
        pd.Series([average_true_range]),
        risk_per_trade_percentage,
        atr_stop_multiplier,
        max_position_fraction,
    )
    position_value_usdt = account_equity_usdt * position_fraction_series.iloc[0]
    return position_value_usdt / close_price


def review(
    signal_event: SignalEvent,
    current_base_asset_balance: float,
    account_equity_usdt: float,
    engine_parameters: dict,
) -> OrderEvent | RejectionEvent | None:
    """
    三種結果(不是兩種) :
    - 目標倉位與當前倉位相同 → None(無需動作)
    - 不同且在風控上限內 → OrderEvent
    - 不同但超過風控上限 → RejectionEvent(只可能發生在買進方向, 賣出方向天然受限於實際持倉)
    """
    current_position = determine_current_position(
        current_base_asset_balance, signal_event.latest_close_price
    )
    if signal_event.target_position == current_position:
        return None

    if signal_event.target_position == 0:
        # 多單 → 空手: 全部平倉, 不重新跑風險計算(compute_buy_quantity 是進場用的風險換算, 不適用平倉)
        return OrderEvent(
            symbol=signal_event.symbol, side="SELL", quantity=current_base_asset_balance
        )

    # 空手 → 多單: 用固定風險公式反推買進數量
    buy_quantity = compute_buy_quantity(
        account_equity_usdt,
        signal_event.latest_close_price,
        signal_event.latest_average_true_range,
        engine_parameters["risk_per_trade_percentage"],
        engine_parameters["atr_stop_multiplier"],
        engine_parameters["max_position_fraction"],
    )
    notional_value_usdt = buy_quantity * signal_event.latest_close_price
    maximum_allowed_notional_usdt = (
        engine_parameters["initial_capital"] * engine_parameters["max_position_fraction"]
    )
    if notional_value_usdt > maximum_allowed_notional_usdt:
        return RejectionEvent(
            symbol=signal_event.symbol,
            reason=(
                f"買進名目金額 {notional_value_usdt:.2f} USDT 超過風控上限 "
                f"{maximum_allowed_notional_usdt:.2f} USDT"
            ),
        )
    return OrderEvent(symbol=signal_event.symbol, side="BUY", quantity=buy_quantity)
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest tests/test_paper_trading_risk_agent.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add 04_paper_trading/agents/risk_agent.py tests/test_paper_trading_risk_agent.py
git commit -m "feat: add risk_agent with position-size cap check"
git push
```

---

### Task 7: execution_agent.py — 真實下單與成交確認

**Files:**
- Create: `04_paper_trading/agents/execution_agent.py`
- Test: `tests/test_paper_trading_execution_agent.py`

**Interfaces:**
- Consumes: `events.OrderEvent`, `FillEvent`, `FailEvent` (Task 1) ; `binance_testnet_client.place_market_order`, `get_order_status`, `round_quantity_to_step_size` (Task 4) 。
- Produces: `execute(order_event: OrderEvent, symbol_filters: dict) -> FillEvent | FailEvent` — Task 8 的 `run_once.py` 會呼叫 `execution_agent.execute(order_event, symbol_filters)`。

- [ ] **Step 1: 寫失敗測試**

Create `tests/test_paper_trading_execution_agent.py`:

```python
"""execution_agent.execute 的單元測試 — monkeypatch 掉 binance_testnet_client 的真實網路呼叫"""
import execution_agent
from events import FailEvent, FillEvent, OrderEvent

SYMBOL_FILTERS = {"step_size": 0.0001, "min_notional": 10.0}


def test_execute_returns_fill_event_when_immediately_filled(monkeypatch):
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

    assert isinstance(result, FillEvent)
    assert result.order_id == "123"
    assert result.average_price == 50_000.0


def test_execute_returns_fail_event_when_exchange_rejects_order(monkeypatch):
    order_event = OrderEvent(symbol="BTCUSDT", side="BUY", quantity=0.05)
    monkeypatch.setattr(
        execution_agent,
        "place_market_order",
        lambda symbol, side, quantity: (400, {"code": -1013, "msg": "Filter failure: MIN_NOTIONAL"}),
    )

    result = execution_agent.execute(order_event, SYMBOL_FILTERS)

    assert isinstance(result, FailEvent)
    assert "MIN_NOTIONAL" in result.reason


def test_execute_polls_until_filled_when_initial_status_is_new(monkeypatch):
    order_event = OrderEvent(symbol="BTCUSDT", side="BUY", quantity=0.05)
    monkeypatch.setattr(
        execution_agent,
        "place_market_order",
        lambda symbol, side, quantity: (200, {"orderId": 123, "status": "NEW"}),
    )
    monkeypatch.setattr(execution_agent.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        execution_agent,
        "get_order_status",
        lambda symbol, order_id: (
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

    assert isinstance(result, FillEvent)


def test_execute_returns_fail_event_when_status_stays_unknown(monkeypatch):
    order_event = OrderEvent(symbol="BTCUSDT", side="BUY", quantity=0.05)
    monkeypatch.setattr(
        execution_agent,
        "place_market_order",
        lambda symbol, side, quantity: (200, {"orderId": 123, "status": "NEW"}),
    )
    monkeypatch.setattr(execution_agent.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        execution_agent, "get_order_status", lambda symbol, order_id: (200, {"status": "NEW"})
    )

    result = execution_agent.execute(order_event, SYMBOL_FILTERS)

    assert isinstance(result, FailEvent)
    assert "狀態不明" in result.reason


def test_execute_returns_fail_event_when_rounded_quantity_is_zero():
    order_event = OrderEvent(symbol="BTCUSDT", side="BUY", quantity=0.00001)

    result = execution_agent.execute(order_event, {"step_size": 0.001, "min_notional": 10.0})

    assert isinstance(result, FailEvent)
    assert "最小交易單位" in result.reason
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_paper_trading_execution_agent.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'execution_agent'`

- [ ] **Step 3: 建立 `04_paper_trading/agents/execution_agent.py`**

```python
"""
Execution agent — 把核准的 OrderEvent 轉成真實 Binance Testnet 市價單, 並確認成交結果
市價單通常在下單回應中就已包含最終狀態; 只有狀態不明確時才輪詢查詢, 查詢逾時記錄為「狀態不明」
而非放棄或盲目重試 — 盲目重試在「可能已經下單」的狀態下有重複下單風險, 這正是 Phase 3 要暴露的問題類型
"""
import os
import sys
import time

from binance_testnet_client import (
    get_order_status,
    place_market_order,
    round_quantity_to_step_size,
)

_agents_directory = os.path.dirname(os.path.abspath(__file__))
_paper_trading_directory = os.path.dirname(_agents_directory)
sys.path.insert(0, _paper_trading_directory)

from events import FailEvent, FillEvent, OrderEvent  # noqa: E402

MAXIMUM_STATUS_POLL_ATTEMPTS = 5
POLL_INTERVAL_SECONDS = 1.0
TERMINAL_FAILURE_STATUSES = ("CANCELED", "REJECTED", "EXPIRED")


def _compute_average_fill_price(order_status_response: dict) -> float:
    """用累計成交金額除以累計成交數量, 得到這筆市價單的加權平均成交價"""
    executed_quantity = float(order_status_response["executedQty"])
    cumulative_quote_quantity = float(order_status_response["cummulativeQuoteQty"])
    return cumulative_quote_quantity / executed_quantity


def execute(order_event: OrderEvent, symbol_filters: dict) -> FillEvent | FailEvent:
    """
    下真實市價單並確認成交; symbol_filters 來自 binance_testnet_client.get_symbol_filters,
    用其 step_size 把數量裁到合法精度, 避免觸發 LOT_SIZE 過濾規則
    """
    rounded_quantity = round_quantity_to_step_size(
        order_event.quantity, symbol_filters.get("step_size")
    )
    if rounded_quantity <= 0:
        return FailEvent(
            symbol=order_event.symbol,
            reason="裁剪至合法精度後數量為 0, 可能低於最小交易單位",
            raw_exchange_response="",
        )

    status_code, order_response = place_market_order(
        order_event.symbol, order_event.side, rounded_quantity
    )
    if status_code != 200:
        return FailEvent(
            symbol=order_event.symbol,
            reason=order_response.get("msg", f"下單失敗, HTTP {status_code}"),
            raw_exchange_response=str(order_response),
        )

    order_id = order_response["orderId"]
    order_status_response = order_response
    # 輪詢迴圈屬執行層 I/O 控制流程, 非訊號/指標邏輯, 不受向量化規範限制(與 engine.py 的
    # apply_trailing_stop_exit 前例一致)
    for _ in range(MAXIMUM_STATUS_POLL_ATTEMPTS):
        current_status = order_status_response.get("status")
        if current_status == "FILLED":
            return FillEvent(
                symbol=order_event.symbol,
                side=order_event.side,
                quantity=float(order_status_response["executedQty"]),
                average_price=_compute_average_fill_price(order_status_response),
                order_id=str(order_id),
            )
        if current_status in TERMINAL_FAILURE_STATUSES:
            return FailEvent(
                symbol=order_event.symbol,
                reason=f"訂單狀態為 {current_status}",
                raw_exchange_response=str(order_status_response),
            )
        time.sleep(POLL_INTERVAL_SECONDS)
        _, order_status_response = get_order_status(order_event.symbol, order_id)

    return FailEvent(
        symbol=order_event.symbol,
        reason="狀態不明, 需人工核對 (輪詢逾時仍未確認成交)",
        raw_exchange_response=str(order_status_response),
    )
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest tests/test_paper_trading_execution_agent.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add 04_paper_trading/agents/execution_agent.py tests/test_paper_trading_execution_agent.py
git commit -m "feat: add execution_agent for real Testnet order placement"
git push
```

---

### Task 8: run_once.py — 串接四個 agent 的執行腳本

**Files:**
- Create: `04_paper_trading/run_once.py`
- Test: `tests/test_paper_trading_run_once.py`

**Interfaces:**
- Consumes: `data_agent.fetch_latest_candles`, `signal_agent.decide` + `FROZEN_ENGINE_PARAMETERS`, `risk_agent.review`, `execution_agent.execute`, `binance_testnet_client.get_account_balances` + `get_symbol_filters`, `events.OrderEvent` (全部先前任務) 。
- Produces: `run_once(symbol: str = "BTCUSDT") -> dict`, `main() -> None` (CLI 進入點) 。無後續任務依賴此檔案, 這是 Slice 1 的最終交付物。

- [ ] **Step 1: 寫失敗測試**

Create `tests/test_paper_trading_run_once.py`:

```python
"""run_once.py 的編排邏輯測試 — monkeypatch 掉所有 4 個 agent, 只驗證串接順序與紀錄格式正確"""
import json
from datetime import datetime, timezone

import pandas as pd
import pytest

import run_once
from events import FillEvent, OrderEvent, SignalEvent


def _make_signal_event(target_position: int) -> SignalEvent:
    return SignalEvent(
        symbol="BTCUSDT",
        target_position=target_position,
        as_of_timestamp=datetime(2026, 7, 6, tzinfo=timezone.utc),
        latest_close_price=50_000.0,
        latest_average_true_range=1_000.0,
    )


def test_run_once_logs_no_action_when_risk_agent_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(run_once, "LOG_FILE_PATH", str(tmp_path / "run_log.jsonl"))
    monkeypatch.setattr(run_once.data_agent, "fetch_latest_candles", lambda symbol: pd.DataFrame())
    monkeypatch.setattr(
        run_once.signal_agent, "decide", lambda ohlcv_dataframe, symbol: _make_signal_event(0)
    )
    monkeypatch.setattr(
        run_once.binance_testnet_client,
        "get_account_balances",
        lambda: {"BTC": 0.0, "USDT": 10_000.0},
    )
    monkeypatch.setattr(run_once.risk_agent, "review", lambda *args, **kwargs: None)

    record = run_once.run_once("BTCUSDT")

    assert record["risk_decision"]["type"] == "NoActionNeeded"
    assert record["execution_result"] is None


def test_run_once_executes_order_when_risk_agent_approves(tmp_path, monkeypatch):
    monkeypatch.setattr(run_once, "LOG_FILE_PATH", str(tmp_path / "run_log.jsonl"))
    monkeypatch.setattr(run_once.data_agent, "fetch_latest_candles", lambda symbol: pd.DataFrame())
    monkeypatch.setattr(
        run_once.signal_agent, "decide", lambda ohlcv_dataframe, symbol: _make_signal_event(1)
    )
    monkeypatch.setattr(
        run_once.binance_testnet_client,
        "get_account_balances",
        lambda: {"BTC": 0.0, "USDT": 10_000.0},
    )
    approved_order = OrderEvent(symbol="BTCUSDT", side="BUY", quantity=0.05)
    monkeypatch.setattr(run_once.risk_agent, "review", lambda *args, **kwargs: approved_order)
    monkeypatch.setattr(
        run_once.binance_testnet_client,
        "get_symbol_filters",
        lambda symbol: {"step_size": 0.0001, "min_notional": 10.0},
    )
    fill_event = FillEvent(
        symbol="BTCUSDT", side="BUY", quantity=0.05, average_price=50_000.0, order_id="123"
    )
    monkeypatch.setattr(
        run_once.execution_agent, "execute", lambda order_event, symbol_filters: fill_event
    )

    record = run_once.run_once("BTCUSDT")

    assert record["risk_decision"]["type"] == "OrderEvent"
    assert record["execution_result"]["type"] == "FillEvent"
    assert record["execution_result"]["order_id"] == "123"


def test_run_once_logs_and_reraises_when_data_agent_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(run_once, "LOG_FILE_PATH", str(tmp_path / "run_log.jsonl"))

    def _raise_connection_error(symbol):
        raise ConnectionError("模擬網路逾時")

    monkeypatch.setattr(run_once.data_agent, "fetch_latest_candles", _raise_connection_error)

    with pytest.raises(ConnectionError):
        run_once.run_once("BTCUSDT")

    with open(tmp_path / "run_log.jsonl", encoding="utf-8") as log_file:
        logged_record = json.loads(log_file.readline())
    assert "模擬網路逾時" in logged_record["pipeline_error"]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `pytest tests/test_paper_trading_run_once.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'run_once'`

- [ ] **Step 3: 建立 `04_paper_trading/run_once.py`**

```python
"""
Paper trading Slice 1 執行腳本 — 串接 data → signal → risk → execution 四個 agent 跑一次
手動觸發(非排程) , 每次執行都以交易所真實帳戶狀態核對現有倉位, 重複執行安全(見設計文件冪等性討論)
用法: python run_once.py [--symbol BTCUSDT]
"""
import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)
sys.path.insert(0, os.path.join(_paper_trading_directory, "agents"))

import binance_testnet_client  # noqa: E402
import data_agent  # noqa: E402
import execution_agent  # noqa: E402
import risk_agent  # noqa: E402
import signal_agent  # noqa: E402
from events import OrderEvent  # noqa: E402

DEFAULT_SYMBOL = "BTCUSDT"
BASE_ASSET = "BTC"
QUOTE_ASSET = "USDT"
LOG_FILE_PATH = os.path.join(_paper_trading_directory, "logs", "run_log.jsonl")


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


def run_once(symbol: str = DEFAULT_SYMBOL) -> dict:
    """跑一次完整 pipeline, 回傳並記錄這次執行的結果; 任何階段失敗都會記錄失敗原因後往外拋出"""
    record = {
        "run_started_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
    }
    try:
        ohlcv_dataframe = data_agent.fetch_latest_candles(symbol)
        signal_event = signal_agent.decide(ohlcv_dataframe, symbol)
        record["signal"] = _serialize_event(signal_event)

        account_balances = binance_testnet_client.get_account_balances()
        current_base_asset_balance = account_balances.get(BASE_ASSET, 0.0)
        current_quote_asset_balance = account_balances.get(QUOTE_ASSET, 0.0)
        account_equity_usdt = (
            current_quote_asset_balance
            + current_base_asset_balance * signal_event.latest_close_price
        )

        risk_decision = risk_agent.review(
            signal_event,
            current_base_asset_balance,
            account_equity_usdt,
            signal_agent.FROZEN_ENGINE_PARAMETERS,
        )
        record["risk_decision"] = _serialize_event(risk_decision)

        if isinstance(risk_decision, OrderEvent):
            symbol_filters = binance_testnet_client.get_symbol_filters(symbol)
            execution_result = execution_agent.execute(risk_decision, symbol_filters)
            record["execution_result"] = _serialize_event(execution_result)
        else:
            record["execution_result"] = None
    except Exception as error:
        record["pipeline_error"] = str(error)
        _append_log_record(record)
        raise
    _append_log_record(record)
    return record


def main() -> None:
    argument_parser = argparse.ArgumentParser(
        description="跑一次紙上交易 pipeline (data agent → signal agent → risk agent → execution agent)"
    )
    argument_parser.add_argument(
        "--symbol", default=DEFAULT_SYMBOL, help=f"交易對, 預設 {DEFAULT_SYMBOL}"
    )
    arguments = argument_parser.parse_args()

    try:
        record = run_once(arguments.symbol)
    except Exception as error:
        print(f"執行失敗: {error}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(record, indent=2, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 執行測試確認通過**

Run: `pytest tests/test_paper_trading_run_once.py -v`
Expected: 3 passed

- [ ] **Step 5: 執行完整測試套件, 確認整個專案沒有連帶破壞**

Run: `pytest tests/ -v`
Expected: 全部通過

- [ ] **Step 6: Commit**

```bash
git add 04_paper_trading/run_once.py tests/test_paper_trading_run_once.py
git commit -m "feat: add run_once orchestrator wiring all 4 paper trading agents"
git push
```

---

### Task 9: 真實 Binance Testnet 手動驗證, 更新 ROADMAP

**Files:**
- Modify: `project_manage/ROADMAP.md` (勾選已完成項目, 更新 data_agent 描述)
- 無新程式碼

**Interfaces:**
- 無 (此任務是手動驗證與文件更新, 不產生後續任務依賴的介面) 。

這是本切片唯一牽涉真實外部系統(即使是 Testnet 假資金) 的步驟, 需要你在場觀察執行結果, 而非無人值守自動跑。

- [ ] **Step 1: 確認 `.env` 憑證已備妥**

Run:
```bash
cd /home/ubuntu/jerome/quant-trading-system
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
assert os.getenv('BINANCE_TESTNET_API_KEY'), '缺少 BINANCE_TESTNET_API_KEY'
assert os.getenv('BINANCE_TESTNET_SECRET'), '缺少 BINANCE_TESTNET_SECRET'
print('憑證已備妥')
"
```
Expected: `憑證已備妥`

- [ ] **Step 2: 實際執行一次 pipeline**

Run:
```bash
cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading
python3 run_once.py --symbol BTCUSDT
```
Expected: 印出一份 JSON 摘要, 三種結果皆算成功 (證明管線接通即為本切片目標, 不要求一定要買到東西) :
- `risk_decision.type` 為 `"NoActionNeeded"`(目標倉位與當前一致, 無需動作) , 或
- `execution_result.type` 為 `"FillEvent"`(真的下單並成交) , 或
- `execution_result.type` 為 `"FailEvent"` 且 `reason` 是可辨識的交易所拒絕原因(例如 MIN_NOTIONAL) — 這也是有效結果, 代表管線接通且正確地把交易所的真實限制回報出來

若拋出未預期例外(非上述三種結果) , 記錄下完整錯誤訊息, 這代表 pipeline 本身有缺陷需要回頭修, 不算完成。

- [ ] **Step 3: 檢查執行紀錄檔**

Run: `cat /home/ubuntu/jerome/quant-trading-system/04_paper_trading/logs/run_log.jsonl`
Expected: 至少一行 JSON, 欄位包含 `run_started_at`, `symbol`, `signal`, `risk_decision`, `execution_result`。

- [ ] **Step 4: 驗證冪等性 (idempotency) — 立刻再跑一次**

Run:
```bash
cd /home/ubuntu/jerome/quant-trading-system/04_paper_trading
python3 run_once.py --symbol BTCUSDT
```
Expected: 這次 `risk_decision.type` 應為 `"NoActionNeeded"`(因為第一次執行後, 若有成交, 帳戶倉位已與目標一致) , 證明重複執行安全, 不會重複下單。

- [ ] **Step 5: 更新 `project_manage/ROADMAP.md`**

把:
```markdown
### 搭建 Agent 系統(`04_paper_trading/agents/`)

- [ ] `data_agent.py`: WebSocket 实时数据拉取 → 标准化 OHLCV DataFrame
- [ ] `signal_agent.py`: 在最新数据上运行策略 → SignalEvent(方向, 强度, 标的)
- [ ] `risk_agent.py`: 风控审核, 硬性规则, 不可绕过 → OrderEvent 或 RejectionEvent
- [ ] `execution_agent.py`: 执行订单, 记录结果 → FillEvent 或 FailEvent + 报警
```

改成:

```markdown
### 搭建 Agent 系統(`04_paper_trading/agents/`)

- [x] `data_agent.py`: REST 輪詢(polling) 拉取最新 K 線 → 標準化 OHLCV DataFrame(Slice 1 改用輪詢, 不用 WebSocket; exp_002 策略以日線決策, 不需要次秒級數據, 見 `docs/superpowers/specs/2026-07-06-phase3-paper-trading-slice1-design.md`)
- [x] `signal_agent.py`: 在最新數據上運行凍結的 exp_002 策略 → SignalEvent(目標倉位, 標的, 收盤價, ATR)
- [x] `risk_agent.py`: 比對目標倉位與當前倉位, 套用倉位大小上限檢查 → OrderEvent, RejectionEvent 或 None(完整風控規則留待後續切片)
- [x] `execution_agent.py`: 對 Binance Testnet 執行真實市價單, 記錄結果 → FillEvent 或 FailEvent(報警留待監控切片)
```

(順手把這個小節原本混入的簡體字改成與全文一致的繁體中文。)

- [ ] **Step 6: Commit**

```bash
git add project_manage/ROADMAP.md
git commit -m "docs: check off Phase 3 slice 1 agent tasks in ROADMAP"
git push
```

---

## Self-Review 紀錄

- **Spec coverage**: 設計文件的 7 個章節(元件, 資料流 5 步, 錯誤處理 5 類, 測試分工) 都能對應到至少一個任務; 唯一的補充是 Task 8 額外加了 pipeline 失敗時「記錄後往外拋出」的錯誤處理, 對應設計文件「數據抓取失敗或逾時」條款, 原設計文件未寫出具體程式碼, 此處補完。
- **Placeholder scan**: 已通篇檢查, 無 TBD / TODO, 每個程式碼區塊皆為完整可執行內容。
- **Type consistency**: `SignalEvent` / `OrderEvent` / `RejectionEvent` / `FillEvent` / `FailEvent` 的欄位, 以及 `fetch_latest_candles` / `decide` / `review` / `execute` 的參數與回傳型別, 已核對 Task 1, 5, 6, 7, 8 之間逐一對齊, 無改名不一致的情形。
