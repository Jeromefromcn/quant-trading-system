"""
Telegram 警報 — 對 Telegram Bot API 發送文字訊息, 用於每日熔斷與數據異常保護規則觸發時通知使用者
與 binance_testnet_client.py 相同手法, 從 .env 讀取憑證; 發送失敗只記錄, 不往外拋例外 —
警報是否送達不該推翻或中止一個已經正確做出的風控決策
"""
import os

import requests
from dotenv import load_dotenv

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
_repository_root = os.path.dirname(_paper_trading_directory)
load_dotenv(os.path.join(_repository_root, ".env"))

TELEGRAM_API_BASE_URL = "https://api.telegram.org"
REQUEST_TIMEOUT_SECONDS = 10


def send_alert(message: str) -> None:
    """
    發送一則文字訊息到設定好的 Telegram 聊天; 缺少憑證, 網路例外, 或非 200 回應皆只印出清楚的
    失敗訊息並返回, 不拋出例外(避免警報通道故障連帶讓風控決策已經完成的這次執行以例外中止)
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print(f"Telegram 警報未發送(缺少憑證) , 原始訊息: {message}")
        return

    url = f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/sendMessage"
    try:
        response = requests.post(
            url, json={"chat_id": chat_id, "text": message}, timeout=REQUEST_TIMEOUT_SECONDS
        )
        if response.status_code != 200:
            print(f"Telegram 警報發送失敗, HTTP {response.status_code}: {response.text}")
    except requests.exceptions.RequestException as network_error:
        # 例外字串可能含有下單網址, 網址內嵌 bot_token, 印出前先遮蔽, 避免真實憑證外洩到終端機/日誌
        sanitized_error_message = str(network_error).replace(bot_token, "***")
        print(f"Telegram 警報發送時發生網路例外: {sanitized_error_message}, 原始訊息: {message}")
