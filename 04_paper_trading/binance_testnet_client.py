"""
Binance Testnet 交易客戶端 — 簽名 (signed) REST 呼叫, 用於紙上交易 (paper trading) 查詢帳戶與下單
與 02_data/fetchers/binance_fetcher.py 的公開行情端點不同, 這裡的端點需要 API Key 簽名驗證,
使用 HMAC(Hash-based Message Authentication Code) -SHA256 手動簽名, 不引入 python-binance/ccxt,
延續本專案偏好手刻 REST 呼叫, 依賴透明的風格(參見 factor_regression.py 手刻 OLS 迴歸的選擇)
"""
import decimal
import hashlib
import hmac
import os
import time
import urllib.parse

import requests
from dotenv import load_dotenv

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
_repository_root = os.path.dirname(_paper_trading_directory)
load_dotenv(os.path.join(_repository_root, ".env"))

BASE_URL = "https://testnet.binance.vision"
REQUEST_TIMEOUT_SECONDS = 30


def _get_credentials() -> tuple[str, str]:
    """從 .env 讀取 Binance Testnet 憑證, 缺少時直接報錯提示先設定"""
    api_key = os.getenv("BINANCE_TESTNET_API_KEY")
    api_secret = os.getenv("BINANCE_TESTNET_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError(
            "缺少 Binance Testnet 憑證, 請先在 .env 填入 BINANCE_TESTNET_API_KEY 與 BINANCE_TESTNET_SECRET"
        )
    return api_key, api_secret


def _signed_request(http_method: str, path: str, params: dict) -> tuple[int, dict]:
    """
    對需要驗證的端點發出簽名請求, 回傳 (HTTP 狀態碼, 解析後的 JSON)
    刻意不對非 2xx 狀態呼叫 raise_for_status, 讓呼叫端可以檢查交易所回傳的錯誤內容
    (例如 LOT_SIZE / MIN_NOTIONAL 過濾失敗) , 只有真正的網路層例外才會往外拋
    """
    api_key, api_secret = _get_credentials()
    signed_parameters = dict(params)
    signed_parameters["timestamp"] = int(time.time() * 1000)
    query_string = urllib.parse.urlencode(signed_parameters)
    signature = hmac.new(
        api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    query_string_with_signature = f"{query_string}&signature={signature}"

    url = f"{BASE_URL}{path}?{query_string_with_signature}"
    response = requests.request(
        http_method,
        url,
        headers={"X-MBX-APIKEY": api_key},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return response.status_code, response.json()


def get_account_balances() -> dict:
    """查詢帳戶餘額, 回傳 {資產代號: 可用餘額} 字典, 只含餘額不為零的資產"""
    status_code, response_body = _signed_request("GET", "/api/v3/account", {})
    if status_code != 200:
        raise RuntimeError(f"查詢帳戶餘額失敗: HTTP {status_code}, {response_body}")
    return {
        balance["asset"]: float(balance["free"])
        for balance in response_body["balances"]
        if float(balance["free"]) > 0
    }


def get_symbol_filters(symbol: str) -> dict:
    """
    查詢交易對的下單規則, 回傳 {"step_size": 數量最小級距, "min_notional": 最小下單金額}
    這是公開端點, 不需簽名; Binance 不同時期用 MIN_NOTIONAL 或 NOTIONAL 命名同一種過濾規則, 兩者都嘗試讀取
    """
    response = requests.get(
        f"{BASE_URL}/api/v3/exchangeInfo",
        params={"symbol": symbol},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    symbol_info = response.json()["symbols"][0]
    step_size = None
    min_notional = None
    for filter_definition in symbol_info["filters"]:
        if filter_definition["filterType"] == "LOT_SIZE":
            step_size = float(filter_definition["stepSize"])
        elif filter_definition["filterType"] in ("MIN_NOTIONAL", "NOTIONAL"):
            min_notional = float(
                filter_definition.get("minNotional", filter_definition.get("notional"))
            )
    return {"step_size": step_size, "min_notional": min_notional}


def round_quantity_to_step_size(quantity: float, step_size: float | None) -> float:
    """
    把下單數量向下裁到 step_size 的整數倍, 避免觸發 Binance 的 LOT_SIZE 過濾規則
    用 Decimal(十進位) 運算取代直接浮點數除乘, 避免浮點數尾數雜訊
    (例如 0.123456 除乘 0.0001 若用原生浮點數運算, 會得到 0.12340000000000001 這種格式,
    送給 Binance 下單 API 很可能被 LOT_SIZE 過濾規則拒絕)
    純函數, 不牽涉網路請求, 可獨立單元測試
    """
    if step_size is None or step_size <= 0:
        return quantity
    quantity_as_decimal = decimal.Decimal(str(quantity))
    step_size_as_decimal = decimal.Decimal(str(step_size))
    number_of_steps = int(quantity_as_decimal / step_size_as_decimal)
    return float(number_of_steps * step_size_as_decimal)


def _format_quantity_for_request(quantity: float) -> str:
    """
    把數量格式化成固定小數點字串(絕不用科學記號) , 避免像 4e-05 這種 Binance 無法解析的格式送出
    先用 Decimal 從數量的字串表示還原, 再輸出定點記法(f 格式一律固定小數點) , 去除多餘的尾隨零
    """
    quantity_as_decimal = decimal.Decimal(str(quantity))
    formatted = format(quantity_as_decimal, "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted or "0"


def place_market_order(symbol: str, side: str, quantity: float) -> tuple[int, dict]:
    """
    下市價單, 參數 side 為 "BUY" 或 "SELL"
    數量格式化成定點小數字串, 避免浮點數雜訊或科學記號讓 Binance 拒單
    回傳 (HTTP 狀態碼, 交易所回應 JSON) , 不拋例外, 由呼叫端(execution_agent) 判斷成敗
    """
    return _signed_request(
        "POST",
        "/api/v3/order",
        {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": _format_quantity_for_request(quantity),
        },
    )


def get_order_status(symbol: str, order_id: int) -> tuple[int, dict]:
    """查詢訂單目前狀態, 回傳 (HTTP 狀態碼, 交易所回應 JSON) """
    return _signed_request("GET", "/api/v3/order", {"symbol": symbol, "orderId": order_id})
