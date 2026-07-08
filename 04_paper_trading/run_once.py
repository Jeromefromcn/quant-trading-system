"""
Paper trading Slice 2 執行腳本 — 對 BTC/USDT 與 ETH/USDT 兩個標的一次執行
data → signal → risk → execution. 收集階段先跑完兩個標的的 data/signal(含逐標的數據異常檢查) ,
再交給 risk_agent 一次性做 portfolio 決策(最大同時持倉數與相關性限制等跨標的規則需要看到
所有標的才能判斷) , 最後執行核准的訂單. 任一標的的數據抓取失敗只影響該標的本身, 不中止其他標的
(與 Slice 1 單標的「整段失敗」不同, 見設計文件錯誤處理段落) . 手動觸發(非排程) , 每次執行都以
交易所真實帳戶狀態核對現有倉位, 重複執行安全(見設計文件冪等性討論)
用法: python run_once.py
"""
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)
sys.path.insert(0, os.path.join(_paper_trading_directory, "agents"))

import binance_testnet_client  # noqa: E402
import daily_risk_state  # noqa: E402
import data_agent  # noqa: E402
import execution_agent  # noqa: E402
import risk_agent  # noqa: E402
import signal_agent  # noqa: E402
import telegram_alerts  # noqa: E402
from events import OrderEvent  # noqa: E402

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
QUOTE_ASSET = "USDT"
BAR_INTERVAL = timedelta(days=1)
LOG_FILE_PATH = os.path.join(_paper_trading_directory, "logs", "run_log.jsonl")
DAILY_STATE_FILE_PATH = os.path.join(_paper_trading_directory, "logs", "daily_risk_state.json")

RISK_LIMITS = {
    "max_loss_per_trade_fraction": 0.015,
    "max_daily_loss_fraction": 0.04,
    "max_positions_by_market": {"crypto": 3, "stocks": 5},
    "max_correlation": 0.8,
}


def _base_asset_from_symbol(symbol: str) -> str:
    """從交易對代號取出基礎資產代號, 例如 "BTCUSDT" -> "BTC"(本專案交易對一律以 USDT 報價)"""
    return symbol.removesuffix(QUOTE_ASSET)


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


def run_once(symbols: list = None) -> dict:
    """
    跑一次完整 pipeline : 對每個標的收集 data/signal(含逐標的數據異常檢查) , 交給 risk_agent
    一次性做 portfolio 決策, 再執行核准的訂單.
    已知簡化: 若某標的本次抓取失敗且該標的目前有實際持倉, 其價值不計入 account_equity_usdt,
    這會讓淨值被低估, 使每日熔斷更容易觸發而非更難觸發, 是保守(安全) 的失敗方向, 而非危險方向
    """
    symbols = symbols if symbols is not None else SYMBOLS
    record = {"run_started_at": datetime.now(timezone.utc).isoformat(), "symbols": {}}

    daily_state = daily_risk_state.load_daily_state(DAILY_STATE_FILE_PATH)
    account_balances = binance_testnet_client.get_account_balances()

    signal_events = {}
    stale_symbols = {}
    close_price_histories = {}
    current_base_asset_balances = {}
    fetch_failures = {}

    for symbol in symbols:
        try:
            ohlcv_dataframe = data_agent.fetch_latest_candles(symbol)
        except Exception as fetch_error:
            fetch_failures[symbol] = str(fetch_error)
            continue

        close_price_histories[symbol] = ohlcv_dataframe["close"]
        last_candle_open_time = (
            ohlcv_dataframe["open_time"].iloc[-1].to_pydatetime().replace(tzinfo=timezone.utc)
        )
        current_time = datetime.now(timezone.utc)
        is_fresh = risk_agent.check_data_staleness(last_candle_open_time, current_time, BAR_INTERVAL)
        if not is_fresh:
            stale_symbols[symbol] = risk_agent.compute_staleness_detail(
                last_candle_open_time, current_time, BAR_INTERVAL
            )
            continue

        signal_event = signal_agent.decide(ohlcv_dataframe, symbol)
        signal_events[symbol] = signal_event
        current_base_asset_balances[symbol] = account_balances.get(
            _base_asset_from_symbol(symbol), 0.0
        )

    account_equity_usdt = account_balances.get(QUOTE_ASSET, 0.0) + sum(
        current_base_asset_balances[symbol] * signal_events[symbol].latest_close_price
        for symbol in signal_events
    )

    current_utc_date = datetime.now(timezone.utc).date().isoformat()
    if daily_risk_state.should_reset_for_new_day(daily_state.get("utc_date"), current_utc_date):
        daily_state = {"utc_date": current_utc_date, "equity_at_day_start_usdt": account_equity_usdt}
        daily_risk_state.save_daily_state(DAILY_STATE_FILE_PATH, daily_state)
    day_start_equity_usdt = daily_state["equity_at_day_start_usdt"]

    record["account_equity_usdt"] = account_equity_usdt
    record["day_start_equity_usdt"] = day_start_equity_usdt
    record["risk_limits"] = RISK_LIMITS
    record["engine_parameters"] = signal_agent.FROZEN_ENGINE_PARAMETERS
    record["fetch_failures"] = fetch_failures
    record["stale_symbols"] = stale_symbols

    circuit_breaker_triggered = not risk_agent.check_daily_circuit_breaker(
        account_equity_usdt, day_start_equity_usdt, RISK_LIMITS["max_daily_loss_fraction"]
    )
    record["circuit_breaker_triggered"] = circuit_breaker_triggered
    if circuit_breaker_triggered:
        telegram_alerts.send_alert(
            f"每日虧損熔斷已觸發: 帳戶淨值從 {day_start_equity_usdt:.2f} USDT "
            f"降至 {account_equity_usdt:.2f} USDT, 停止今日所有交易"
        )
    if stale_symbols:
        telegram_alerts.send_alert(f"數據異常保護觸發, 暫停信號生成: {', '.join(stale_symbols)}")

    decisions = risk_agent.review_portfolio(
        signal_events,
        stale_symbols,
        current_base_asset_balances,
        account_equity_usdt,
        day_start_equity_usdt,
        close_price_histories,
        signal_agent.FROZEN_ENGINE_PARAMETERS,
        RISK_LIMITS,
    )

    for symbol, decision in decisions.items():
        symbol_record = {"risk_decision": _serialize_event(decision)}
        if symbol in signal_events:
            signal_event = signal_events[symbol]
            symbol_record["signal"] = {
                "target_position": signal_event.target_position,
                "latest_close_price": signal_event.latest_close_price,
                "latest_average_true_range": signal_event.latest_average_true_range,
                "as_of_timestamp": signal_event.as_of_timestamp,
            }
            symbol_record["current_base_asset_balance"] = current_base_asset_balances[symbol]
        if isinstance(decision, OrderEvent):
            symbol_filters = binance_testnet_client.get_symbol_filters(symbol)
            execution_result = execution_agent.execute(decision, symbol_filters)
            symbol_record["execution_result"] = _serialize_event(execution_result)
        else:
            symbol_record["execution_result"] = None
        record["symbols"][symbol] = symbol_record

    _append_log_record(record)
    return record


def main() -> None:
    try:
        record = run_once()
    except Exception as error:
        print(f"執行失敗: {error}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(record, indent=2, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
