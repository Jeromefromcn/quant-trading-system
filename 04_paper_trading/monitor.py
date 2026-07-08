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
            except (json.JSONDecodeError, KeyError, ValueError, TypeError) as parse_error:
                print(f"略過無法解析的第 {line_number} 行: {parse_error}", file=sys.stderr)
                continue
            if run_started_at.astimezone(timezone.utc).date() == target_date:
                matched_records.append(record)
    return matched_records


def _format_daily_report(records: list[dict], target_date: date) -> str:
    """
    把 _load_records_for_date 過濾出的當日 records 組成人類可讀的每日報告文字.
    當日無任何紀錄時只回傳標題 + 提示, 其餘段落略過(仍要發送, 讓使用者能分辨
    今天真的沒交易, 與排程或 monitor.py 本身沒跑這兩種情況)
    """
    header_line = f"每日報告 ({target_date.isoformat()} UTC)"
    if not records:
        return f"{header_line}\n當日無任何執行紀錄"

    fill_lines = []
    for record in records:
        run_time_label = datetime.fromisoformat(record["run_started_at"]).strftime("%H:%M UTC")
        for symbol, symbol_record in record["symbols"].items():
            execution_result = symbol_record["execution_result"]
            if execution_result is not None and execution_result["type"] == "FillEvent":
                side_label = "買入" if execution_result["side"] == "BUY" else "賣出"
                fill_lines.append(
                    f"{run_time_label} {symbol}: {side_label} {execution_result['quantity']} "
                    f"@ {execution_result['average_price']}"
                )
    fill_section = "\n".join(fill_lines) if fill_lines else "今日無成交"

    rejection_count = sum(
        1
        for record in records
        for symbol_record in record["symbols"].values()
        if symbol_record["risk_decision"]["type"] == "RejectionEvent"
    )
    stats_line = f"今日排程執行 {len(records)} / 預期 {EXPECTED_RUNS_PER_DAY} 次, 風控拒絕 {rejection_count} 次"

    day_start_equity = records[0]["day_start_equity_usdt"]
    day_end_equity = records[-1]["account_equity_usdt"]
    equity_change_percentage = (day_end_equity - day_start_equity) / day_start_equity * 100
    equity_line = (
        f"帳戶淨值從 {day_start_equity:.2f} 變化至 {day_end_equity:.2f} USDT "
        f"({equity_change_percentage:+.2f}%)"
    )

    latest_symbols = records[-1]["symbols"]
    position_lines = []
    for symbol, symbol_record in latest_symbols.items():
        if "current_base_asset_balance" not in symbol_record:
            continue
        balance = symbol_record["current_base_asset_balance"]
        if balance != 0:
            latest_close_price = symbol_record["signal"]["latest_close_price"]
            position_lines.append(f"{symbol}: {balance} (約 {balance * latest_close_price:.2f} USDT)")
    position_section = "\n".join(position_lines) if position_lines else "目前無持倉"

    staleness_trigger_count = sum(1 for record in records if record["stale_symbols"])
    circuit_breaker_trigger_count = sum(1 for record in records if record["circuit_breaker_triggered"])
    health_line = (
        f"系統健康: 數據異常保護觸發 {staleness_trigger_count} 次, "
        f"每日熔斷觸發 {circuit_breaker_trigger_count} 次"
    )

    return "\n".join(
        [
            header_line, "", fill_section, "", stats_line, equity_line,
            "", "持倉:", position_section, "", health_line,
        ]
    )


def main() -> None:
    target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    records = _load_records_for_date(LOG_FILE_PATH, target_date)
    report = _format_daily_report(records, target_date)
    telegram_alerts.send_alert(report)
    print(f"每日報告已發送 ({target_date.isoformat()} UTC), 涵蓋 {len(records)} 筆執行紀錄")


if __name__ == "__main__":
    main()
