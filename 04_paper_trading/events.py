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
