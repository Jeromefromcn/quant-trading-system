"""
Phase 3 紙上交易 (paper trading) 美股每日報告 (monitor): 讀取 run_log_stocks.jsonl 中前一個美東交易日
的執行紀錄, 彙總成每日報告透過 Telegram 發送. crontab 每 15 分鐘觸發一次, 由 main() 內部用美東時間判斷
是否落在開盤前目標窗口, 且「昨天」是否真的有交易紀錄(market_open=True), 兩者皆成立才發送, 不依賴 cron
本身的時區/星期欄位解讀, 也不需要額外狀態檔做去重(見 docs/superpowers/specs/2026-07-13-phase3-stocks-
scheduler-timezone-fix-design.md 的「去重設計」段落).
與加密貨幣版 monitor.py 的關鍵差異: 這裡顯示的是已送出的開盤委託(SubmittedEvent, 尚未確認成交),
不是已確認成交; 是否成交由今日實際持倉(來自查詢到的真實 Alpaca 倉位) 間接反映.
見設計文件 docs/superpowers/specs/2026-07-10-phase3-us-stocks-paper-trading-design.md
用法: python3 monitor_stocks.py
"""
import json
import os
import sys
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _paper_trading_directory)

import telegram_alerts  # noqa: E402

LOG_FILE_PATH = os.path.join(_paper_trading_directory, "logs", "run_log_stocks.jsonl")
US_EASTERN_TIMEZONE = ZoneInfo("America/New_York")
EXPECTED_RUNS_PER_DAY = 1  # 美股排程每個交易日只觸發一次(收盤後), 與加密貨幣的每 4 小時一次不同
TARGET_WINDOW_START_EASTERN = time(7, 45)
TARGET_WINDOW_END_EASTERN = time(8, 0)


def _is_within_target_window(now_eastern: datetime) -> bool:
    """判斷現在美東時間是否落在開盤前目標執行窗口 [07:45, 08:00) 內"""
    return TARGET_WINDOW_START_EASTERN <= now_eastern.time() < TARGET_WINDOW_END_EASTERN


def _load_records_for_date(log_file_path: str, target_date: date) -> list[dict]:
    """
    逐行讀 log_file_path(jsonl), 只保留 market_date_eastern 等於 target_date 的紀錄(以美東交易日
    為準, 不是 UTC 日曆天, 因收盤後執行時 UTC 已跨到隔天). 檔案不存在時回傳空列表; 個別行解析失敗或
    不是 dict 時略過該行並印出警告, 不中止整份報告
    """
    if not os.path.exists(log_file_path):
        return []
    matched_records = []
    target_date_string = target_date.isoformat()
    with open(log_file_path, "r", encoding="utf-8") as log_file:
        for line_number, line in enumerate(log_file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise TypeError("record 不是 dict")
                market_date_eastern = record["market_date_eastern"]
            except (json.JSONDecodeError, KeyError, TypeError) as parse_error:
                print(f"略過無法解析的第 {line_number} 行: {parse_error}", file=sys.stderr)
                continue
            if market_date_eastern == target_date_string:
                matched_records.append(record)
    return matched_records


def _format_daily_report(records: list[dict], target_date: date) -> str:
    """把 _load_records_for_date 過濾出的當日 records 組成人類可讀的每日報告文字"""
    header_line = f"美股每日報告 ({target_date.isoformat()} 美東交易日)"
    if not records:
        return f"{header_line}\n當日無任何執行紀錄"

    latest_record = records[-1]
    if not latest_record.get("market_open", True):
        return f"{header_line}\n今日美股休市, 無交易"

    submission_lines = []
    for record in records:
        for symbol, symbol_record in record["symbols"].items():
            execution_result = symbol_record.get("execution_result")
            if execution_result is not None and execution_result["type"] == "SubmittedEvent":
                side_label = "買入" if execution_result["side"] == "BUY" else "賣出"
                price_label = (
                    f"@ {execution_result['limit_price']} 限價"
                    if execution_result.get("limit_price") is not None
                    else "市價"
                )
                submission_lines.append(
                    f"{symbol}: {side_label} {execution_result['quantity']} 股 {price_label} "
                    f"開盤委託已送出 (order_id={execution_result['order_id']})"
                )
    submission_section = "\n".join(submission_lines) if submission_lines else "今日無新委託送出"

    rejection_count = sum(
        1
        for record in records
        for symbol_record in record["symbols"].values()
        if symbol_record["risk_decision"]["type"] == "RejectionEvent"
    )
    stats_line = f"今日排程執行 {len(records)} / 預期 {EXPECTED_RUNS_PER_DAY} 次, 風控拒絕 {rejection_count} 次"

    day_start_equity = latest_record["day_start_equity_usd"]
    day_end_equity = latest_record["account_equity_usd"]
    equity_change_percentage = (day_end_equity - day_start_equity) / day_start_equity * 100
    equity_line = (
        f"帳戶淨值從 {day_start_equity:.2f} 變化至 {day_end_equity:.2f} USD "
        f"({equity_change_percentage:+.2f}%)"
    )

    position_lines = []
    for symbol, symbol_record in latest_record["symbols"].items():
        if "current_share_balance" not in symbol_record:
            continue
        balance = symbol_record["current_share_balance"]
        if balance != 0:
            latest_close_price = symbol_record["signal"]["latest_close_price"]
            position_lines.append(f"{symbol}: {balance} 股 (約 {balance * latest_close_price:.2f} USD)")
    position_section = "\n".join(position_lines) if position_lines else "目前無持倉"

    staleness_trigger_count = sum(1 for record in records if record["stale_symbols"])
    circuit_breaker_trigger_count = sum(1 for record in records if record["circuit_breaker_triggered"])
    health_line = (
        f"系統健康: 數據異常保護觸發 {staleness_trigger_count} 次, "
        f"每日熔斷觸發 {circuit_breaker_trigger_count} 次"
    )

    return "\n".join(
        [
            header_line, "", submission_section, "", stats_line, equity_line,
            "", "持倉:", position_section, "", health_line,
        ]
    )


def main(now_eastern: datetime | None = None) -> None:
    now_eastern = now_eastern if now_eastern is not None else datetime.now(US_EASTERN_TIMEZONE)
    if not _is_within_target_window(now_eastern):
        return
    target_date = (now_eastern - timedelta(days=1)).date()
    records = _load_records_for_date(LOG_FILE_PATH, target_date)
    if not any(record.get("market_open") for record in records):
        return
    report = _format_daily_report(records, target_date)
    telegram_alerts.send_alert(report)
    print(f"美股每日報告已發送 ({target_date.isoformat()}), 涵蓋 {len(records)} 筆執行紀錄")


if __name__ == "__main__":
    main()
