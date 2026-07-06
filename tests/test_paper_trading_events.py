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
