"""
Stock execution agent: 把核准的 OrderEvent 轉成真實 Alpaca Paper Trading 開盤委託單.
買進用開盤限價單(limit-on-open, LOO, 限價 = 收盤時算出的價格), 賣出(出場) 用開盤市價單
(market-on-open, MOO): 出場的目的是降低風險曝險, 保證成交比價格保護更重要, 見設計文件說明.
委託送出時市場尚未開盤, 不會立即成交, 回傳 SubmittedEvent(已送出, 未確認成交) 而非 FillEvent,
成交與否留給次日執行時查詢真實倉位自然核對(見設計文件的次日的自然核對機制段落).
"""
import os
import sys

import requests

from alpaca_paper_trading_client import (
    place_limit_on_open_order,
    place_market_on_open_order,
    round_quantity_down_to_whole_shares,
)

_agents_directory = os.path.dirname(os.path.abspath(__file__))
_paper_trading_directory = os.path.dirname(_agents_directory)
sys.path.insert(0, _paper_trading_directory)

from events import FailEvent, OrderEvent, SubmittedEvent  # noqa: E402


def execute(order_event: OrderEvent) -> SubmittedEvent | FailEvent:
    """
    把核准的 OrderEvent 轉成 Alpaca 開盤委託單; 買進用限價(LOO), 賣出用市價(MOO)
    數量先向下裁到整數股(不支援分數股), 裁剪後為 0 直接回報失敗, 不送出空單
    """
    rounded_quantity = round_quantity_down_to_whole_shares(order_event.quantity)
    if rounded_quantity <= 0:
        return FailEvent(
            symbol=order_event.symbol,
            reason="裁剪至整數股後數量為 0, 部位過小無法下單",
            raw_exchange_response="",
        )

    try:
        if order_event.side == "BUY":
            status_code, order_response = place_limit_on_open_order(
                order_event.symbol, order_event.side, rounded_quantity, order_event.limit_price
            )
        else:
            status_code, order_response = place_market_on_open_order(
                order_event.symbol, order_event.side, rounded_quantity
            )
    except requests.exceptions.RequestException as network_error:
        # 下單請求本身發生網路例外: 無法得知委託是否已送達交易所, 不能盲目重送(可能造成重複下單)
        return FailEvent(
            symbol=order_event.symbol,
            reason=f"下單請求發生網路例外, 無法確認委託是否已送達交易所, 需人工核對: {network_error}",
            raw_exchange_response="",
        )

    if status_code not in (200, 201):
        return FailEvent(
            symbol=order_event.symbol,
            reason=order_response.get("message", f"下單失敗, HTTP {status_code}"),
            raw_exchange_response=str(order_response),
        )

    return SubmittedEvent(
        symbol=order_event.symbol,
        side=order_event.side,
        quantity=float(rounded_quantity),
        order_id=str(order_response["id"]),
        limit_price=order_event.limit_price,
    )
