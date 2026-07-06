"""
每日風控狀態 — 記錄「今天(UTC) 開始時的帳戶淨值」, 供每日虧損熔斷(daily circuit breaker) 規則
計算「當日累計虧損」用. `run_once.py` 刻意保持無狀態(每次都查詢交易所真實狀態, 不信任本地記憶) ,
但交易所現貨帳戶沒有「今天損益」這種端點可查, 這份小型本地快取只補這一個交易所查不到的基準點,
本身不是真相來源 — 真相來源永遠是查詢到的當前淨值, 這份檔案只回答「要跟哪一個基準比」
"""
import json
import os


def should_reset_for_new_day(stored_utc_date, current_utc_date: str) -> bool:
    """比對儲存的 UTC 日期字串與現在的 UTC 日期字串, 不同(含尚無儲存值) 即需要重置每日基準"""
    return stored_utc_date != current_utc_date


def load_daily_state(file_path: str) -> dict:
    """
    讀取每日風控狀態檔; 檔案不存在或內容無法解析時, 回傳空字典(呼叫端會視為「尚無基準」, 直接重置) ,
    不因本地快取損壞而中止或阻擋交易 — 這份檔案是本地快取, 不是真相來源
    """
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as state_file:
            return json.load(state_file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_daily_state(file_path: str, state: dict) -> None:
    """把每日風控狀態寫入檔案, 目錄不存在時自動建立"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as state_file:
        json.dump(state, state_file)
