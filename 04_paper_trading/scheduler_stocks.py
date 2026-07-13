"""
Phase 3 紙上交易 (paper trading) 美股排程器 (scheduler): 包住 run_once_stocks.run_once() 的排程
安全網, 提供防重疊執行的鎖(lock) 與失敗告警. crontab 每 15 分鐘觸發一次, 由 _should_run_now 內部
用美東時間判斷是否落在收盤後目標窗口且今天尚未執行, 不依賴 cron 本身的時區/星期欄位解讀(該解讀在
本機不可靠, 見 docs/superpowers/specs/2026-07-13-phase3-stocks-scheduler-timezone-fix-design.md).
非交易日(run_once_stocks 回報 market_open=False) 不發送 Telegram 摘要, 避免週末/假日連續洗版
用法: python3 scheduler_stocks.py
"""
import fcntl
import json
import os
import sys
import traceback
from datetime import datetime, time

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)

import run_once_stocks  # noqa: E402
import telegram_alerts  # noqa: E402

SCHEDULER_LOCK_PATH = os.path.join(_paper_trading_directory, "logs", "scheduler_stocks.lock")
NOTIFY_RUN_SUMMARY = True  # 交易日執行完成後是否發送 Telegram 執行摘要, 設為 False 可關閉此通知

TARGET_WINDOW_START_EASTERN = time(16, 35)
TARGET_WINDOW_END_EASTERN = time(17, 35)


def _is_within_target_window(now_eastern: datetime) -> bool:
    """判斷現在美東時間是否落在收盤後目標執行窗口 [16:35, 17:35) 內"""
    return TARGET_WINDOW_START_EASTERN <= now_eastern.time() < TARGET_WINDOW_END_EASTERN


def _has_already_run_today(log_file_path: str, today_eastern: str) -> bool:
    """讀 run_log_stocks.jsonl 最後一行, 判斷今天(美東日期) 是否已經執行過一次"""
    if not os.path.exists(log_file_path):
        return False
    with open(log_file_path, "r", encoding="utf-8") as log_file:
        non_blank_lines = [line for line in log_file if line.strip()]
    if not non_blank_lines:
        return False
    try:
        last_record = json.loads(non_blank_lines[-1])
    except json.JSONDecodeError:
        return False
    if not isinstance(last_record, dict):
        return False
    return last_record.get("market_date_eastern") == today_eastern


def _should_run_now(now_eastern: datetime, log_file_path: str) -> bool:
    """兩個條件皆成立才需要真的執行: 現在落在目標窗口內, 且今天(美東日期) 還沒執行過"""
    if not _is_within_target_window(now_eastern):
        return False
    today_eastern = now_eastern.date().isoformat()
    return not _has_already_run_today(log_file_path, today_eastern)


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


def main(now_eastern: datetime | None = None) -> None:
    now_eastern = now_eastern if now_eastern is not None else datetime.now(run_once_stocks.US_EASTERN_TIMEZONE)
    if not _should_run_now(now_eastern, run_once_stocks.LOG_FILE_PATH):
        sys.exit(0)
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
