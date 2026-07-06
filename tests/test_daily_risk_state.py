"""daily_risk_state 的單元測試 — 純函式的重置判斷邏輯, 以及本機檔案 I/O 的讀寫往返"""
import os

import daily_risk_state


def test_should_reset_for_new_day_when_date_differs():
    assert daily_risk_state.should_reset_for_new_day("2026-07-05", "2026-07-06") is True


def test_should_reset_for_new_day_when_date_matches():
    assert daily_risk_state.should_reset_for_new_day("2026-07-06", "2026-07-06") is False


def test_should_reset_for_new_day_when_no_stored_date():
    assert daily_risk_state.should_reset_for_new_day(None, "2026-07-06") is True


def test_load_daily_state_returns_empty_dict_when_file_missing(tmp_path):
    missing_file_path = str(tmp_path / "does_not_exist.json")
    assert daily_risk_state.load_daily_state(missing_file_path) == {}


def test_load_daily_state_returns_empty_dict_when_file_corrupted(tmp_path):
    corrupted_file_path = tmp_path / "corrupted.json"
    corrupted_file_path.write_text("{not valid json", encoding="utf-8")
    assert daily_risk_state.load_daily_state(str(corrupted_file_path)) == {}


def test_save_and_load_daily_state_round_trip(tmp_path):
    state_file_path = str(tmp_path / "nested_directory" / "daily_risk_state.json")
    state = {"utc_date": "2026-07-06", "equity_at_day_start_usdt": 10_000.0}

    daily_risk_state.save_daily_state(state_file_path, state)
    loaded_state = daily_risk_state.load_daily_state(state_file_path)

    assert loaded_state == state
    assert os.path.exists(state_file_path)


def test_save_daily_state_with_bare_filename_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = {"utc_date": "2026-07-06", "equity_at_day_start_usdt": 10_000.0}

    daily_risk_state.save_daily_state("bare_filename.json", state)
    loaded_state = daily_risk_state.load_daily_state("bare_filename.json")

    assert loaded_state == state
