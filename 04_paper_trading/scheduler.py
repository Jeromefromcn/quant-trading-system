"""
Phase 3 紙上交易 (paper trading) 排程器 (scheduler) : 包住 run_once.run_once() 的排程安全網,
提供防重疊執行的鎖 (lock) 與失敗告警, 讓 crontab 可以無人值守地每 4 小時觸發一次.
見設計文件 docs/superpowers/specs/2026-07-08-phase3-paper-trading-scheduler-design.md
用法: python3 scheduler.py
"""
import fcntl
import os
import sys
import traceback

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)

import run_once  # noqa: E402
import telegram_alerts  # noqa: E402

SCHEDULER_LOCK_PATH = os.path.join(_paper_trading_directory, "logs", "scheduler.lock")


class SchedulerLockedError(Exception):
    """上一次排程執行尚未結束 (鎖仍被持有), 本次應跳過, 不與上一次併發執行"""


def run_scheduled(lock_file_path: str) -> dict:
    """
    以 fcntl.flock(LOCK_EX | LOCK_NB) 對 lock_file_path 嘗試取得非阻塞的獨占鎖
    (exclusive lock, 非阻塞 non-blocking). 取得鎖時呼叫 run_once.run_once() 並回傳其結果;
    鎖隨本函式的檔案物件被釋放或 process 結束而釋放(crash 時核心也會自動釋放,
    不會留下無法清除的殘留鎖). 搶不到鎖時拋出 SchedulerLockedError, 不自己發告警
    (告警交給 main() 統一處理, 方便測試以 mock 驗證)
    """
    os.makedirs(os.path.dirname(lock_file_path), exist_ok=True)
    lock_file = open(lock_file_path, "w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        raise SchedulerLockedError(f"排程鎖 {lock_file_path} 已被持有, 上一次執行可能尚未結束")
    return run_once.run_once()


def main() -> None:
    try:
        record = run_scheduled(SCHEDULER_LOCK_PATH)
    except SchedulerLockedError as locked_error:
        telegram_alerts.send_alert("排程跳過: 上一次執行尚未結束")
        print(str(locked_error), file=sys.stderr)
        sys.exit(0)
    except Exception as error:
        telegram_alerts.send_alert(f"排程執行失敗: {error}")
        traceback.print_exc()
        sys.exit(1)
    print(f"排程執行完成, 處理標的數: {len(record['symbols'])}")
    sys.exit(0)


if __name__ == "__main__":
    main()
