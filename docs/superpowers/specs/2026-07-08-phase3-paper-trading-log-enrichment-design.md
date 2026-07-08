# Phase 3 紙上交易 (paper trading) 執行紀錄補齊設計文件

日期 : 2026-07-08
狀態 : 已核准 (approved), 待寫實作計劃 (implementation plan)

## 背景 (background)

Slice 1、Slice 2 與排程器 (scheduler) 已完成並上線 (見 `docs/superpowers/specs/2026-07-06-phase3-paper-trading-slice1-design.md`、`2026-07-06-phase3-paper-trading-slice2-risk-rules-design.md`、`2026-07-08-phase3-paper-trading-scheduler-design.md`), 每 4 小時自動對 BTC/USDT、ETH/USDT 執行一次完整 pipeline, 執行結果寫入 `04_paper_trading/logs/run_log.jsonl`.

目前這份紀錄只夠回答這次執行做了什麼決策、有沒有成交, 不足以支援日後的量化分析. 具體檢視現有紀錄與交易鏈路 (`run_once.py`、`events.py`、`risk_agent.py`、`execution_agent.py`) 後, 找出以下缺口 :

- **沒有帳戶淨值快照** : `run_once()` 內部已經算出 `account_equity_usdt`, 但沒寫進 `record`, 無法用這份紀錄重建權益曲線 (equity curve)、計算 Sharpe 或回撤 (drawdown). 目前唯一存有淨值的地方是 `logs/daily_risk_state.json`, 但它每天被覆蓋一次, 不是歷史序列
- **沒有訊號當時的上下文** : `signal_agent.decide()` 算出的 `target_position`、`latest_close_price`、`latest_average_true_range` 只留在記憶體, 沒有序列化進 log
- **沒有手續費 (commission)** : Binance 市價單成交回應本來就含 `fills` 陣列 (`commission`、`commissionAsset` 逐筆列出), 但 `execution_agent.py` 完全沒解析, `FillEvent` 也沒有對應欄位, 無法做手續費後 (net of fees) 的真實績效分析
- **風控拒絕沒有數值依據** : `RejectionEvent.reason` 只有文字說明 (例如單筆潛在虧損超過風控上限), 沒有附上實際算出的數值(潛在虧損比例、相關係數、當日虧損比例等), 無法用來檢視風控參數設得鬆或緊
- **沒有參數快照** : 若未來策略參數 (`FROZEN_ENGINE_PARAMETERS`) 或風控上限 (`RISK_LIMITS`) 調整, 舊 log 無法對應當時是用哪組參數跑的

本文件只處理把既有可得資訊補進 log, 與讓風控判斷函式額外暴露計算數值, 不改變任何交易或風控的判斷結果 (哪些單會下、哪些單會被擋, 邏輯上跟補齊前完全一樣), 純粹是可觀測性 (observability) 的補強.

## 目標與範圍 (goal and scope)

**目標** : 讓 `run_log.jsonl` 之後可以直接拿來重建權益曲線、算 Sharpe/回撤、檢視手續費後績效、檢視風控參數鬆緊, 不需要另外回頭查交易所或重新計算.

**本切片範圍內 (依補齊深度分 5 個 tier, 全部一起做)** :

- **Tier 1 : 帳戶權益快照** : `record` 新增 `account_equity_usdt`、`day_start_equity_usdt`
- **Tier 2 : 訊號上下文** : 有算出訊號的標的, `record["symbols"][symbol]` 新增 `signal` 子欄位
- **Tier 3 : 手續費** : `FillEvent` 新增 `commission`、`commission_asset`, 從 Binance 成交回應的 `fills` 陣列解析
- **Tier 4 : 風控決策數值化** : `RejectionEvent` 新增 `computed_value`、`limit_value`, 6 種拒絕情境都附上對應數值
- **Tier 5 : 參數快照** : `record` 新增 `risk_limits`、`engine_parameters`, 記錄當次執行實際用的參數字典

**明確排除, 留給後續切片** :

- 不新增任何風控規則, 不調整任何現有風控上限的數值
- 不改變任何 `check_*` 函式的 bool 回傳合約(既有測試不用重寫, 只加新測試)
- `monitor.py` 每日彙總報告 (獨立關注點, 不在本文件範圍)
- 不處理歷史上已經寫入的舊格式 log 行 (`run_log.jsonl` 裡補齊前的紀錄維持原樣, 新格式只從補齊後的執行開始生效; 分析時需要自行處理欄位是否存在)

## 元件 (components)

### `events.py` (資料結構變動)

```python
@dataclass
class RejectionEvent:
    """risk_agent 認為該交易, 但被風控規則擋下"""
    symbol: str
    reason: str
    computed_value: float | None = None  # 觸發拒絕當下的實際計算值, 與 reason 描述的是同一種單位
    limit_value: float | None = None     # 對應的風控上限值, 與 computed_value 同單位


@dataclass
class FillEvent:
    """execution_agent 確認成交"""
    symbol: str
    side: str
    quantity: float
    average_price: float
    order_id: str
    commission: float = 0.0      # 這筆訂單的總手續費, 從成交回應的 fills 陣列加總而得
    commission_asset: str = ""   # 手續費計價資產(例如 "USDT" 或 "BNB")
```

兩個 dataclass 的新欄位都給預設值, 對既有呼叫端(直接用位置參數或關鍵字建構、不傳這兩個新欄位)完全向下相容, 既有測試不需要修改建構呼叫的部分.

### `risk_agent.py` (Tier 4 : 計算與判斷分離)

新增 3 個 pure helper 函式, 各自把算出數值的部分從既有 `check_*` 函式抽出來; 既有 `check_*` 函式內部改呼叫這些 helper 取得數值再比較, **對外的 bool 回傳合約完全不變**, 既有測試不需要修改:

```python
def compute_potential_loss_usdt(order_quantity, average_true_range, atr_stop_multiplier) -> float:
    """算出這筆開倉若觸及停損會虧損多少 USDT(數量 x 停損距離) , 與 check_max_loss_per_trade 內部算法相同"""
    return order_quantity * atr_stop_multiplier * average_true_range


def compute_daily_loss_fraction(account_equity_usdt, day_start_equity_usdt) -> float:
    """算出當日虧損比例; 當日開始淨值為 0 或負值時視為無法判斷, 回傳 0.0(保守, 不誤判為熔斷)"""
    if day_start_equity_usdt <= 0:
        return 0.0
    return (day_start_equity_usdt - account_equity_usdt) / day_start_equity_usdt


def compute_max_correlation_against_existing_positions(
    candidate_close_price_series, existing_position_close_price_series
) -> float | None:
    """
    回傳候選標的與所有現有持倉中最高的日報酬率相關係數(correlation coefficient) ;
    無現有持倉時回傳 None(代表無需比較) ; 任一現有持倉重疊數據不足 2 筆或相關係數算出 NaN
    (例如某段價格完全不變) 時同樣回傳 None(代表數據不足以計算, 而非數值為 0)
    """
```

`check_max_loss_per_trade`、`check_daily_circuit_breaker`、`check_correlation_limit` 三個函式內部改呼叫對應 helper, 回傳值判斷邏輯不變.

`check_correlation_limit` 目前把重疊數據不足 / NaN, 與相關係數真的超過上限, 這兩種情況都回傳同一個 `False`, `review_portfolio` 也共用同一句 `reason` 文字. 這次拆成兩種 `reason`, 讓未來分析能分辨是數據不夠判斷, 還是真的相關性太高:

- 相關係數確實超過上限 : `reason="與現有持倉相關係數超過風控上限"`, `computed_value`= helper 算出的相關係數, `limit_value=max_correlation`
- 重疊數據不足或無法計算(NaN) : `reason="相關係數無法計算(數據不足或無變化), 風控保守拒絕"`, `computed_value=None`, `limit_value=max_correlation`

`review_portfolio` 6 種拒絕情境的 `computed_value`/`limit_value` 對應關係 :

| 拒絕情境 | `computed_value` | `limit_value` | 單位 |
|---|---|---|---|
| 每日熔斷觸發 | `compute_daily_loss_fraction(...)` | `risk_limits["max_daily_loss_fraction"]` | 比例(fraction) |
| 數據過期 | 見下方 `compute_staleness_detail` | 同左 | 秒 |
| 單筆潛在虧損超限 | `compute_potential_loss_usdt(...) / account_equity_usdt` | `risk_limits["max_loss_per_trade_fraction"]` | 比例(fraction) |
| 最大同時持倉數超限 | `positions_in_same_market_count`(既有局部變數) | `risk_limits["max_positions_by_market"][market_type]` | 個數(count) |
| 相關係數超限 | helper 回傳的相關係數 | `risk_limits["max_correlation"]` | 相關係數(-1~1) |
| 相關係數無法計算 | `None` | `risk_limits["max_correlation"]` | 相關係數(-1~1) |
| 買進名目金額超限 | `notional_value_usdt`(既有局部變數) | `maximum_allowed_notional_usdt`(既有局部變數) | USDT |

名目金額超限這條, `reason` 字串裡本來就已經嵌入這兩個數值, 這次維持字串不變, 額外把同樣的數值也放進結構化欄位, 兩者並存(字串給人看, 結構化欄位給程式分析).

### `risk_agent.py` 新增 staleness 細節 helper, `run_once.py` 呼叫端調整

```python
def compute_staleness_detail(
    last_candle_open_time, current_time, bar_interval=timedelta(days=1), staleness_multiplier=1.5
) -> dict:
    """
    回傳 {"time_since_close_seconds": 已過期秒數, "threshold_seconds": 門檻秒數} ,
    與 check_data_staleness 的計算邏輯相同, 供 run_once.py 記錄過期細節用
    """
```

`check_data_staleness` 內部改呼叫這個 helper 取得兩個秒數再比較, bool 回傳合約不變.

`run_once.py` 目前逐標的呼叫 `check_data_staleness` 判斷是否過期, 只把過期的標的名稱加進 `stale_symbols`(`list[str]`). 這次改成同時呼叫 `compute_staleness_detail`, 把 `stale_symbols` 從 `list[str]` 改成 `dict[str, dict]`(標的 → `compute_staleness_detail` 回傳的字典). `review_portfolio` 的 `stale_symbols` 參數型別也從 `list` 改成 `dict`, 內部 `for symbol in stale_symbols` 的既有寫法對 dict 一樣成立(走 key), 建構 `RejectionEvent` 時額外帶入 `computed_value=stale_symbols[symbol]["time_since_close_seconds"]`、`limit_value=stale_symbols[symbol]["threshold_seconds"]`.

這是本次唯一一個會改變 `review_portfolio` 對外參數型別的地方, 呼叫端(`run_once.py`)與既有測試(`tests/test_paper_trading_risk_agent.py`、`tests/test_paper_trading_run_once.py`)裡建構 `stale_symbols` 引數的地方都要同步從 list 改成 dict.

### `execution_agent.py` (Tier 3 : 手續費解析)

```python
def _compute_total_commission(order_status_response: dict) -> tuple[float, str]:
    """
    加總成交回應 fills 陣列裡每筆的 commission, 回傳 (加總後手續費, 手續費計價資產) ;
    已知簡化 : 假設同一筆訂單裡所有 fills 的 commissionAsset 一致(實務上單一訂單極少見混用計價資產) ,
    直接取第一筆 fill 的 commissionAsset, 不逐筆比對是否一致
    """
```

`execute()` 組裝 `FillEvent` 時呼叫這個函式填入 `commission`、`commission_asset`. `fills` 陣列不存在或為空(理論上 `FILLED` 狀態必定有 `fills`, 但外部 API 回應不保證格式) 時回傳 `(0.0, "")`, 不拋例外, 與這個檔案既有外部回應格式異常不中止流程的風格一致.

### `run_once.py` (Tier 1/2/5 : 純新增欄位)

`record` 頂層(執行完帳戶淨值與每日狀態計算後) 新增 :

```python
record["account_equity_usdt"] = account_equity_usdt
record["day_start_equity_usdt"] = day_start_equity_usdt
record["risk_limits"] = RISK_LIMITS
record["engine_parameters"] = signal_agent.FROZEN_ENGINE_PARAMETERS
```

組裝每個標的的 `symbol_record` 時, 若該標的存在於 `signal_events`(代表這次執行有算出訊號, 排除 fetch 失敗與數據過期兩種情況), 新增 :

```python
symbol_record["signal"] = {
    "target_position": signal_events[symbol].target_position,
    "latest_close_price": signal_events[symbol].latest_close_price,
    "latest_average_true_range": signal_events[symbol].latest_average_true_range,
    "as_of_timestamp": signal_events[symbol].as_of_timestamp,
}
symbol_record["current_base_asset_balance"] = current_base_asset_balances[symbol]
```

`as_of_timestamp` 是 `datetime`, 沿用既有 `_append_log_record` 已經在用的 `json.dumps(..., default=str, ...)` 機制序列化, 不需要額外處理.

## 補齊後的完整範例紀錄

```json
{
  "run_started_at": "2026-07-08T12:00:00.000000+00:00",
  "account_equity_usdt": 57681.50,
  "day_start_equity_usdt": 57500.00,
  "risk_limits": {
    "max_loss_per_trade_fraction": 0.015,
    "max_daily_loss_fraction": 0.04,
    "max_positions_by_market": {"crypto": 3, "stocks": 5},
    "max_correlation": 0.8
  },
  "engine_parameters": {"risk_per_trade_percentage": 0.01, "atr_stop_multiplier": 3.0, "...": "..."},
  "symbols": {
    "BTCUSDT": {
      "signal": {
        "target_position": 1,
        "latest_close_price": 62927.3,
        "latest_average_true_range": 1200.5,
        "as_of_timestamp": "2026-07-08T00:00:00+00:00"
      },
      "current_base_asset_balance": 0.0,
      "risk_decision": {"type": "OrderEvent", "symbol": "BTCUSDT", "side": "BUY", "quantity": 0.05},
      "execution_result": {
        "type": "FillEvent", "symbol": "BTCUSDT", "side": "BUY", "quantity": 0.05,
        "average_price": 62930.1, "order_id": "13701966",
        "commission": 3.146, "commission_asset": "USDT"
      }
    }
  },
  "fetch_failures": {},
  "stale_symbols": {},
  "circuit_breaker_triggered": false
}
```

## 錯誤處理與已知簡化 (error handling and known simplifications)

- 補齊前已經寫入 `run_log.jsonl` 的舊格式紀錄不會被回填, 分析程式需要對新欄位用 `.get(...)` 之類的方式容錯處理, 不能假設每一行都有這次新增的欄位
- `_compute_total_commission` 假設單筆訂單所有 `fills` 的 `commissionAsset` 一致, 只取第一筆; 若 Binance 未來對單筆市價單混用多種計價資產計費(目前已知情況下不會發生), 會低估或誤標手續費資產, 是保守的已知簡化, 不是本次要解決的問題
- `compute_max_correlation_against_existing_positions` 與 `compute_staleness_detail` 回傳 `None`/字典的情況, 需與既有 `check_correlation_limit`/`check_data_staleness` 的 bool 判斷邏輯保持數學上一致(同一份輸入, helper 算出的數值與既有函式的 True/False 結論不能互相矛盾), 實作時兩者要共用同一段計算, 不能各自重寫一份

## 測試 (testing)

- `compute_potential_loss_usdt`、`compute_daily_loss_fraction`、`compute_max_correlation_against_existing_positions`、`compute_staleness_detail` 四個新 helper 各自獨立單元測試(數值正確性), 與既有 `check_*` 函式的既有測試分開, 互不影響
- 既有 `check_max_loss_per_trade`/`check_daily_circuit_breaker`/`check_correlation_limit`/`check_data_staleness` 的既有測試檔案不需修改斷言內容(bool 合約不變), 只需確認仍然全部通過
- `review_portfolio` 的 6 種拒絕情境測試(既有 `tests/test_paper_trading_risk_agent.py`), 每種都補上 `computed_value`/`limit_value` 的斷言; `stale_symbols` 從 list 改 dict 後, 既有測試裡建構這個引數的地方同步更新
- `execution_agent` 測試(`tests/test_paper_trading_execution_agent.py`)的成交回應 fixture 補上 `fills` 陣列, 斷言 `FillEvent.commission`/`commission_asset` 正確
- `run_once.py` 既有測試(`tests/test_paper_trading_run_once.py`)補上新欄位斷言(`account_equity_usdt`、`signal` 子欄位等), 並確認 `stale_symbols` 型別改變後既有測試仍然通過
- 全專案 `pytest tests/ -v` 確認無回歸
