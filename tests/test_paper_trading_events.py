"""events.py 的型別化事件 (typed events) 冒煙測試: 確保每個事件的欄位不被意外改名或刪除"""
from datetime import datetime, timezone

from events import FailEvent, FillEvent, OrderEvent, RejectionEvent, SignalEvent, SubmittedEvent


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
