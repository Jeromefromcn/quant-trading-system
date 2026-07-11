"""
Phase 3 紙上交易 (paper trading) 美股執行腳本: 對 VOO 與 QQQ 兩個標的一次執行.
資料流程依序是 data, signal, risk, execution. 與加密貨幣側 run_once.py 架構相同, 差異只在資料來源/執行客戶端
換成 Alpaca, 且核准的開倉單一律走開盤限價/市價委託(limit-on-open / market-on-open), 不做立即市價單.
開頭先檢查今天是否為美股交易日(用美東時間計算, 不依賴伺服器本地時區, 見 US_EASTERN_TIMEZONE),
非交易日安靜跳過, 不產生信號也不查帳戶.
用法: python run_once_stocks.py
"""
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)
sys.path.insert(0, os.path.join(_paper_trading_directory, "agents"))

import alpaca_paper_trading_client  # noqa: E402
import daily_risk_state  # noqa: E402
import risk_agent  # noqa: E402
import signal_agent  # noqa: E402
import stock_data_agent  # noqa: E402
import stock_execution_agent  # noqa: E402
import telegram_alerts  # noqa: E402
from events import OrderEvent  # noqa: E402

SYMBOLS = ["VOO", "QQQ"]
BAR_INTERVAL = timedelta(days=1)
LOG_FILE_PATH = os.path.join(_paper_trading_directory, "logs", "run_log_stocks.jsonl")
DAILY_STATE_FILE_PATH = os.path.join(
    _paper_trading_directory, "logs", "daily_risk_state_stocks.json"
)
# 用美東時間(而非伺服器本地時區) 判斷今天是哪個交易日: 伺服器在 Asia/Hong_Kong, 收盤後(美東 16:35)
# 執行時, 香港當地已跨到隔天, 若用伺服器本地日期查交易日曆會查錯日期; zoneinfo 自動處理夏令/冬令時間轉換
US_EASTERN_TIMEZONE = ZoneInfo("America/New_York")

RISK_LIMITS = {
    "max_loss_per_trade_fraction": 0.015,
    "max_daily_loss_fraction": 0.04,
    "max_positions_by_market": {"crypto": 3, "stocks": 5},
    "max_correlation": 0.8,
}


def _serialize_event(event) -> dict:
    """把 dataclass 事件轉成可寫入 JSON 的字典; 無事件(None, 代表無需動作) 轉成明確標記"""
    if event is None:
        return {"type": "NoActionNeeded"}
    serialized = asdict(event)
    serialized["type"] = type(event).__name__
    return serialized


def _append_log_record(record: dict) -> None:
    """把這次執行紀錄追加寫入 logs/run_log_stocks.jsonl(一行一筆 JSON, gitignore 排除) """
    os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)
    with open(LOG_FILE_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")


def run_once(symbols: list = None) -> dict:
    """
    跑一次完整美股 pipeline: 先確認今天是美股交易日, 再對每個標的收集 data/signal, 交給 risk_agent
    一次性做 portfolio 決策, 核准的開倉單一律送開盤限價/市價委託(LOO/MOO), 不嘗試確認即時成交
    (委託送出時市場尚未開盤); 成交與否由次日執行時查詢真實倉位自然核對
    """
    symbols = symbols if symbols is not None else SYMBOLS
    today_eastern = datetime.now(US_EASTERN_TIMEZONE).date().isoformat()
    record = {
        "run_started_at": datetime.now(timezone.utc).isoformat(),
        "market_date_eastern": today_eastern,
        "symbols": {},
    }

    calendar_entry = alpaca_paper_trading_client.get_todays_calendar_entry(today_eastern)
    if calendar_entry is None:
        record["market_open"] = False
        _append_log_record(record)
        return record
    record["market_open"] = True

    daily_state = daily_risk_state.load_daily_state(DAILY_STATE_FILE_PATH)
    account = alpaca_paper_trading_client.get_account()
    current_positions = alpaca_paper_trading_client.get_positions()

    signal_events = {}
    stale_symbols = {}
    close_price_histories = {}
    fetch_failures = {}

    for symbol in symbols:
        try:
            ohlcv_dataframe = stock_data_agent.fetch_latest_daily_bars(symbol)
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

        signal_events[symbol] = signal_agent.decide(ohlcv_dataframe, symbol)

    account_equity_usd = account["equity"]
    current_share_balances = {
        symbol: current_positions.get(symbol, 0.0) for symbol in signal_events
    }

    if daily_risk_state.should_reset_for_new_day(
        daily_state.get("market_date_eastern"), today_eastern
    ):
        daily_state = {
            "market_date_eastern": today_eastern,
            "equity_at_day_start_usd": account_equity_usd,
        }
        daily_risk_state.save_daily_state(DAILY_STATE_FILE_PATH, daily_state)
    day_start_equity_usd = daily_state["equity_at_day_start_usd"]

    record["account_equity_usd"] = account_equity_usd
    record["day_start_equity_usd"] = day_start_equity_usd
    record["risk_limits"] = RISK_LIMITS
    record["engine_parameters"] = signal_agent.FROZEN_ENGINE_PARAMETERS
    record["fetch_failures"] = fetch_failures
    record["stale_symbols"] = stale_symbols

    circuit_breaker_triggered = not risk_agent.check_daily_circuit_breaker(
        account_equity_usd, day_start_equity_usd, RISK_LIMITS["max_daily_loss_fraction"]
    )
    record["circuit_breaker_triggered"] = circuit_breaker_triggered
    if circuit_breaker_triggered:
        telegram_alerts.send_alert(
            f"[美股] 每日虧損熔斷已觸發: 帳戶淨值從 {day_start_equity_usd:.2f} USD "
            f"降至 {account_equity_usd:.2f} USD, 停止今日所有交易"
        )
    if stale_symbols:
        telegram_alerts.send_alert(f"[美股] 數據異常保護觸發, 暫停信號生成: {', '.join(stale_symbols)}")

    decisions = risk_agent.review_portfolio(
        signal_events,
        stale_symbols,
        current_share_balances,
        account_equity_usd,
        day_start_equity_usd,
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
            symbol_record["current_share_balance"] = current_share_balances[symbol]
        if isinstance(decision, OrderEvent):
            execution_result = stock_execution_agent.execute(decision)
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
