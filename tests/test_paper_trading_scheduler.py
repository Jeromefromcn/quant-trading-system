"""scheduler.py 的排程安全網測試 : 鎖行為與告警分流全程 mock, 不碰真正鎖檔或外部網路"""
import fcntl
import os

import pytest

import scheduler


def test_run_scheduled_calls_run_once_when_lock_available(tmp_path, monkeypatch):
    lock_file_path = str(tmp_path / "scheduler.lock")
    call_count = {"n": 0}

    def _fake_run_once():
        call_count["n"] += 1
        return {"symbols": {}}

    monkeypatch.setattr(scheduler.run_once, "run_once", _fake_run_once)

    result = scheduler.run_scheduled(lock_file_path)

    assert call_count["n"] == 1
    assert result == {"symbols": {}}


def test_run_scheduled_raises_when_lock_already_held(tmp_path, monkeypatch):
    lock_file_path = str(tmp_path / "scheduler.lock")
    holder_file = open(lock_file_path, "w")
    fcntl.flock(holder_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        was_called = {"called": False}
        monkeypatch.setattr(
            scheduler.run_once, "run_once", lambda: was_called.update(called=True)
        )

        with pytest.raises(scheduler.SchedulerLockedError):
            scheduler.run_scheduled(lock_file_path)

        assert was_called["called"] is False
    finally:
        holder_file.close()


def test_main_exits_zero_without_alert_when_successful(monkeypatch):
    monkeypatch.setattr(
        scheduler, "run_scheduled", lambda lock_file_path: {"symbols": {"BTCUSDT": {}}}
    )
    alerts = []
    monkeypatch.setattr(scheduler.telegram_alerts, "send_alert", lambda message: alerts.append(message))

    with pytest.raises(SystemExit) as exit_info:
        scheduler.main()

    assert exit_info.value.code == 0
    assert alerts == []


def test_main_sends_alert_and_exits_zero_when_locked(monkeypatch):
    def _raise_locked(lock_file_path):
        raise scheduler.SchedulerLockedError("鎖仍被持有")

    monkeypatch.setattr(scheduler, "run_scheduled", _raise_locked)
    alerts = []
    monkeypatch.setattr(scheduler.telegram_alerts, "send_alert", lambda message: alerts.append(message))

    with pytest.raises(SystemExit) as exit_info:
        scheduler.main()

    assert exit_info.value.code == 0
    assert len(alerts) == 1
    assert "尚未結束" in alerts[0]


def test_main_sends_alert_and_exits_one_when_run_once_raises(monkeypatch):
    def _raise_unexpected(lock_file_path):
        raise RuntimeError("模擬 API 無回應")

    monkeypatch.setattr(scheduler, "run_scheduled", _raise_unexpected)
    alerts = []
    monkeypatch.setattr(scheduler.telegram_alerts, "send_alert", lambda message: alerts.append(message))

    with pytest.raises(SystemExit) as exit_info:
        scheduler.main()

    assert exit_info.value.code == 1
    assert len(alerts) == 1
    assert "模擬 API 無回應" in alerts[0]
