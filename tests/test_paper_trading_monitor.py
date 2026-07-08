"""monitor.py 的每日報告測試 : 讀檔/日期過濾用 tmp_path, 格式化與發送用手造資料或 mock"""
import json
from datetime import date

import pytest

import monitor


def test_load_records_for_date_filters_by_utc_date_boundary(tmp_path):
    log_file_path = str(tmp_path / "run_log.jsonl")
    record_before_boundary = {"run_started_at": "2026-07-07T23:59:59+00:00", "marker": "yesterday"}
    record_after_boundary = {"run_started_at": "2026-07-08T00:00:01+00:00", "marker": "today"}
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(json.dumps(record_before_boundary) + "\n")
        log_file.write(json.dumps(record_after_boundary) + "\n")

    records = monitor._load_records_for_date(log_file_path, date(2026, 7, 8))

    assert len(records) == 1
    assert records[0]["marker"] == "today"


def test_load_records_for_date_returns_empty_list_when_file_missing(tmp_path):
    missing_log_file_path = str(tmp_path / "does_not_exist.jsonl")

    records = monitor._load_records_for_date(missing_log_file_path, date(2026, 7, 8))

    assert records == []
