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
