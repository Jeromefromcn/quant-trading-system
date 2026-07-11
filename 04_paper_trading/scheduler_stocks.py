"""
Phase 3 紙上交易 (paper trading) 美股排程器 (scheduler): 包住 run_once_stocks.run_once() 的排程
安全網, 提供防重疊執行的鎖(lock) 與失敗告警, 讓 crontab 可以無人值守地在每個美股交易日收盤後觸發一次.
非交易日(run_once_stocks 回報 market_open=False) 不發送 Telegram 摘要, 避免週末/假日連續洗版
見設計文件 docs/superpowers/specs/2026-07-10-phase3-us-stocks-paper-trading-design.md
用法: python3 scheduler_stocks.py
"""
import fcntl
import os
import sys
import traceback

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)

import run_once_stocks  # noqa: E402
import telegram_alerts  # noqa: E402

SCHEDULER_LOCK_PATH = os.path.join(_paper_trading_directory, "logs", "scheduler_stocks.lock")
NOTIFY_RUN_SUMMARY = True  # 交易日執行完成後是否發送 Telegram 執行摘要, 設為 False 可關閉此通知


class SchedulerLockedError(Exception):
    """上一次排程執行尚未結束 (鎖仍被持有), 本次應跳過, 不與上一次併發執行"""


def _format_symbol_line(symbol: str, symbol_record: dict) -> str:
    """把單一標的的 risk_decision / execution_result 轉成摘要訊息裡的一行文字"""
    risk_decision = symbol_record["risk_decision"]
    decision_type = risk_decision["type"]
    if decision_type == "NoActionNeeded":
        return f"{symbol}: 本次無動作"
    if decision_type == "RejectionEvent":
        return (
            f"{symbol}: 交易被風控擋下 ({risk_decision['reason']}, "
            f"實際值={risk_decision['computed_value']}, 上限={risk_decision['limit_value']})"
        )
    execution_result = symbol_record["execution_result"]
    if execution_result["type"] == "SubmittedEvent":
        side_label = "買入" if execution_result["side"] == "BUY" else "賣出"
        return (
            f"{symbol}: {side_label} {execution_result['quantity']} 股委託已送出 "
            f"(order_id={execution_result['order_id']}), 待次日開盤確認成交"
        )
    return f"{symbol}: 下單失敗 ({execution_result['reason']})"


def _format_run_summary(record: dict) -> str:
    """把 run_once_stocks.run_once() 回傳的 record 轉成人類可讀的執行摘要"""
    symbol_records = record["symbols"]
    header_line = f"美股 Paper trading 執行摘要 ({record['run_started_at']})"
    symbol_lines = [
        _format_symbol_line(symbol, symbol_record)
        for symbol, symbol_record in symbol_records.items()
    ]
    return "\n".join([header_line, ""] + symbol_lines)


def run_scheduled(lock_file_path: str) -> dict:
    """
    以 fcntl.flock(LOCK_EX | LOCK_NB) 對 lock_file_path 嘗試取得非阻塞的獨占鎖, 取得鎖時呼叫
    run_once_stocks.run_once() 並回傳其結果; 搶不到鎖時拋出 SchedulerLockedError
    """
    os.makedirs(os.path.dirname(lock_file_path), exist_ok=True)
    lock_file = open(lock_file_path, "w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        raise SchedulerLockedError(f"排程鎖 {lock_file_path} 已被持有, 上一次執行可能尚未結束")
    return run_once_stocks.run_once()


def main() -> None:
    try:
        record = run_scheduled(SCHEDULER_LOCK_PATH)
    except SchedulerLockedError as locked_error:
        telegram_alerts.send_alert("[美股] 排程跳過: 上一次執行尚未結束")
        print(str(locked_error), file=sys.stderr)
        sys.exit(0)
    except Exception as error:
        telegram_alerts.send_alert(f"[美股] 排程執行失敗: {error}")
        traceback.print_exc()
        sys.exit(1)
    if not record.get("market_open", True):
        print("今天非美股交易日, 無需執行")
        sys.exit(0)
    if NOTIFY_RUN_SUMMARY:
        telegram_alerts.send_alert(_format_run_summary(record))
    print(f"排程執行完成, 處理標的數: {len(record['symbols'])}")
    sys.exit(0)


if __name__ == "__main__":
    main()
