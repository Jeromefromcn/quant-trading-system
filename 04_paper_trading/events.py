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
    computed_value: float | None = None  # 觸發拒絕當下的實際計算值, 與 reason 描述的是同一種單位
    limit_value: float | None = None  # 對應的風控上限值, 與 computed_value 同單位


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


@dataclass
class FailEvent:
    """execution_agent 下單或確認失敗 (含狀態不明) """

    symbol: str
    reason: str
    raw_exchange_response: str
