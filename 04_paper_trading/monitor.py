"""
Phase 3 紙上交易 (paper trading) 每日報告 (monitor) : 讀取 run_log.jsonl 中前一個 UTC 日曆天的
所有執行紀錄, 彙總成一則每日報告(成交交易, 執行/拒絕次數統計, 帳戶淨值變化, 持倉明細, 系統健康) ,
透過 Telegram 發送. 由獨立 crontab 於每天 UTC 00:00 觸發, 與 scheduler.py 的排程互不影響.
見設計文件 docs/superpowers/specs/2026-07-08-phase3-paper-trading-monitor-daily-report-design.md
用法: python3 monitor.py
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)

import telegram_alerts  # noqa: E402

LOG_FILE_PATH = os.path.join(_paper_trading_directory, "logs", "run_log.jsonl")
EXPECTED_RUNS_PER_DAY = 6  # 目前 crontab 每 4 小時觸發一次加密貨幣排程, 一天 6 次; 排程頻率改變需同步修改


def _load_records_for_date(log_file_path: str, target_date: date) -> list[dict]:
    """
    逐行讀 log_file_path(jsonl, 每行一筆 run_once() 的執行紀錄) , 只保留 run_started_at
    (UTC 時區, ISO 格式) 落在 target_date 這個 UTC 日曆天的紀錄. 檔案不存在時回傳空列表
    (每日報告不該因為排程還沒跑過而失敗) ; 個別行解析失敗時略過該行並印出警告, 不中止整份報告
    """
    if not os.path.exists(log_file_path):
        return []
    matched_records = []
    with open(log_file_path, "r", encoding="utf-8") as log_file:
        for line_number, line in enumerate(log_file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                run_started_at = datetime.fromisoformat(record["run_started_at"])
            except (json.JSONDecodeError, KeyError, ValueError) as parse_error:
                print(f"略過無法解析的第 {line_number} 行: {parse_error}", file=sys.stderr)
                continue
            if run_started_at.astimezone(timezone.utc).date() == target_date:
                matched_records.append(record)
    return matched_records
