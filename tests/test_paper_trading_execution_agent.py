"""execution_agent.execute 的單元測試 — monkeypatch 掉 binance_testnet_client 的真實網路呼叫"""
import requests

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


def test_execute_returns_fail_event_when_order_status_is_terminal_failure(monkeypatch):
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
        lambda symbol, order_id: (200, {"orderId": 123, "status": "REJECTED"}),
    )

    result = execution_agent.execute(order_event, SYMBOL_FILTERS)

    assert isinstance(result, FailEvent)
    assert "REJECTED" in result.reason


def test_execute_returns_fail_event_when_place_order_raises_network_exception(monkeypatch):
    order_event = OrderEvent(symbol="BTCUSDT", side="BUY", quantity=0.05)

    def _raise_connection_error(symbol, side, quantity):
        raise requests.exceptions.ConnectionError("模擬連線逾時")

    monkeypatch.setattr(execution_agent, "place_market_order", _raise_connection_error)

    result = execution_agent.execute(order_event, SYMBOL_FILTERS)

    assert isinstance(result, FailEvent)
    assert "網路例外" in result.reason


def test_execute_continues_polling_when_get_order_status_raises_network_exception(monkeypatch):
    order_event = OrderEvent(symbol="BTCUSDT", side="BUY", quantity=0.05)
    monkeypatch.setattr(
        execution_agent,
        "place_market_order",
        lambda symbol, side, quantity: (200, {"orderId": 123, "status": "NEW"}),
    )
    monkeypatch.setattr(execution_agent.time, "sleep", lambda seconds: None)

    call_count = {"count": 0}

    def _flaky_get_order_status(symbol, order_id):
        call_count["count"] += 1
        if call_count["count"] == 1:
            raise requests.exceptions.ConnectionError("模擬暫時性連線失敗")
        return (
            200,
            {
                "orderId": 123,
                "status": "FILLED",
                "executedQty": "0.0500",
                "cummulativeQuoteQty": "2500.00",
            },
        )

    monkeypatch.setattr(execution_agent, "get_order_status", _flaky_get_order_status)

    result = execution_agent.execute(order_event, SYMBOL_FILTERS)

    assert isinstance(result, FillEvent)
