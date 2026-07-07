"""telegram_alerts.send_alert 的單元測試 — monkeypatch 掉 requests.post, 不打真實網路請求"""
import telegram_alerts


class _FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def test_send_alert_succeeds_when_api_returns_200(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat-id")
    monkeypatch.setattr(
        telegram_alerts.requests, "post", lambda url, json, timeout: _FakeResponse(200)
    )

    telegram_alerts.send_alert("測試訊息")  # 不應拋出例外


def test_send_alert_does_not_raise_when_network_exception(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat-id")

    def _raise_network_error(url, json, timeout):
        raise telegram_alerts.requests.exceptions.ConnectionError("模擬網路斷線")

    monkeypatch.setattr(telegram_alerts.requests, "post", _raise_network_error)

    telegram_alerts.send_alert("測試訊息")  # 不應拋出例外


def test_send_alert_does_not_raise_when_credentials_missing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    telegram_alerts.send_alert("測試訊息")  # 不應拋出例外, 只印出提示


def test_send_alert_does_not_raise_when_api_returns_non_200(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat-id")
    monkeypatch.setattr(
        telegram_alerts.requests,
        "post",
        lambda url, json, timeout: _FakeResponse(400, "Bad Request: chat not found"),
    )

    telegram_alerts.send_alert("測試訊息")  # 不應拋出例外


def test_send_alert_scrubs_bot_token_from_network_exception_message(monkeypatch, capsys):
    # 網路例外字串常含請求網址, 網址內嵌 bot_token, 印出前必須遮蔽, 否則真實憑證會外洩到終端機
    real_token = "123456789:AAFAKE_SECRET_BOT_TOKEN_xyz"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", real_token)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat-id")

    def _raise_network_error_with_url(url, json, timeout):
        raise telegram_alerts.requests.exceptions.ConnectionError(
            f"Max retries exceeded with url: /bot{real_token}/sendMessage"
        )

    monkeypatch.setattr(telegram_alerts.requests, "post", _raise_network_error_with_url)

    telegram_alerts.send_alert("測試訊息")

    printed_output = capsys.readouterr().out
    assert real_token not in printed_output
    assert "***" in printed_output
