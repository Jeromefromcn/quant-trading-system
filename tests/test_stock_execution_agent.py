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
