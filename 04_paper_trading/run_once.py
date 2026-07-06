"""
Paper trading Slice 1 執行腳本 — 串接 data → signal → risk → execution 四個 agent 跑一次
手動觸發(非排程) , 每次執行都以交易所真實帳戶狀態核對現有倉位, 重複執行安全(見設計文件冪等性討論)
用法: python run_once.py [--symbol BTCUSDT]
"""
import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)
sys.path.insert(0, os.path.join(_paper_trading_directory, "agents"))

import binance_testnet_client  # noqa: E402
import data_agent  # noqa: E402
import execution_agent  # noqa: E402
import risk_agent  # noqa: E402
import signal_agent  # noqa: E402
from events import OrderEvent  # noqa: E402

DEFAULT_SYMBOL = "BTCUSDT"
BASE_ASSET = "BTC"
QUOTE_ASSET = "USDT"
LOG_FILE_PATH = os.path.join(_paper_trading_directory, "logs", "run_log.jsonl")


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


def run_once(symbol: str = DEFAULT_SYMBOL) -> dict:
    """跑一次完整 pipeline, 回傳並記錄這次執行的結果; 任何階段失敗都會記錄失敗原因後往外拋出"""
    record = {
        "run_started_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
    }
    try:
        ohlcv_dataframe = data_agent.fetch_latest_candles(symbol)
        signal_event = signal_agent.decide(ohlcv_dataframe, symbol)
        record["signal"] = _serialize_event(signal_event)

        account_balances = binance_testnet_client.get_account_balances()
        current_base_asset_balance = account_balances.get(BASE_ASSET, 0.0)
        current_quote_asset_balance = account_balances.get(QUOTE_ASSET, 0.0)
        account_equity_usdt = (
            current_quote_asset_balance
            + current_base_asset_balance * signal_event.latest_close_price
        )

        risk_decision = risk_agent.review(
            signal_event,
            current_base_asset_balance,
            account_equity_usdt,
            signal_agent.FROZEN_ENGINE_PARAMETERS,
        )
        record["risk_decision"] = _serialize_event(risk_decision)

        if isinstance(risk_decision, OrderEvent):
            symbol_filters = binance_testnet_client.get_symbol_filters(symbol)
            execution_result = execution_agent.execute(risk_decision, symbol_filters)
            record["execution_result"] = _serialize_event(execution_result)
        else:
            record["execution_result"] = None
    except Exception as error:
        record["pipeline_error"] = str(error)
        _append_log_record(record)
        raise
    _append_log_record(record)
    return record


def main() -> None:
    argument_parser = argparse.ArgumentParser(
        description="跑一次紙上交易 pipeline (data agent → signal agent → risk agent → execution agent)"
    )
    argument_parser.add_argument(
        "--symbol", default=DEFAULT_SYMBOL, help=f"交易對, 預設 {DEFAULT_SYMBOL}"
    )
    arguments = argument_parser.parse_args()

    try:
        record = run_once(arguments.symbol)
    except Exception as error:
        print(f"執行失敗: {error}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(record, indent=2, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
