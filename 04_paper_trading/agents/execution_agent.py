"""
Execution agent — 把核准的 OrderEvent 轉成真實 Binance Testnet 市價單, 並確認成交結果
市價單通常在下單回應中就已包含最終狀態; 只有狀態不明確時才輪詢查詢, 查詢逾時記錄為「狀態不明」
而非放棄或盲目重試 — 盲目重試在「可能已經下單」的狀態下有重複下單風險, 這正是 Phase 3 要暴露的問題類型
"""
import os
import sys
import time

import requests

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

    try:
        status_code, order_response = place_market_order(
            order_event.symbol, order_event.side, rounded_quantity
        )
    except requests.exceptions.RequestException as network_error:
        # 下單請求本身發生網路例外: 無法得知訂單是否已送達交易所, 也拿不到 order_id 可供輪詢,
        # 只能記錄為需人工核對, 絕不能盲目重送(可能造成重複下單)
        return FailEvent(
            symbol=order_event.symbol,
            reason=f"下單請求發生網路例外, 無法確認訂單是否已送達交易所, 需人工核對: {network_error}",
            raw_exchange_response="",
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
        try:
            _, order_status_response = get_order_status(order_event.symbol, order_id)
        except requests.exceptions.RequestException:
            # 查詢狀態時網路例外: 訂單已確定送達交易所(已拿到 order_id), 只是這次查詢失敗,
            # 保留上一輪的狀態不變, 讓迴圈繼續嘗試下一次, 逾時後併入下方「狀態不明」的結論
            continue

    return FailEvent(
        symbol=order_event.symbol,
        reason="狀態不明, 需人工核對 (輪詢逾時仍未確認成交)",
        raw_exchange_response=str(order_status_response),
    )
