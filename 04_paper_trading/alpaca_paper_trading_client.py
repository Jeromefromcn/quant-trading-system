"""
Alpaca Paper Trading 交易客戶端: 用 API-Key 標頭驗證的 REST 呼叫, 查詢帳戶, 倉位, 交易日曆與下單
與 02_data/fetchers/alpaca_fetcher.py 的行情端點(data.alpaca.markets) 不同, 這裡打的是交易端點
(paper-api.alpaca.markets), 但沿用同一組 .env 憑證(ALPACA_PAPER_API_KEY / ALPACA_PAPER_SECRET_KEY) .
比 Binance 的 HMAC(Hash-based Message Authentication Code) 簽名簡單, 只需固定的兩個標頭, 不需組簽名字串
"""
import os

import requests
from dotenv import load_dotenv

_paper_trading_directory = os.path.dirname(os.path.abspath(__file__))
_repository_root = os.path.dirname(_paper_trading_directory)
load_dotenv(os.path.join(_repository_root, ".env"))

REQUEST_TIMEOUT_SECONDS = 30


def _get_base_url() -> str:
    """從 .env 讀取交易端點, 缺省時退回 Alpaca Paper Trading 的官方端點"""
    return os.getenv("ALPACA_PAPER_BASE_URL", "https://paper-api.alpaca.markets")


def _build_authentication_headers() -> dict:
    """組出 Alpaca 要求的認證標頭, 缺少憑證時直接報錯提示先設定 .env"""
    api_key = os.getenv("ALPACA_PAPER_API_KEY")
    secret_key = os.getenv("ALPACA_PAPER_SECRET_KEY")
    if not api_key or not secret_key or "your_" in api_key:
        raise RuntimeError(
            "缺少 Alpaca 憑證, 請先在 .env 填入 ALPACA_PAPER_API_KEY 與 ALPACA_PAPER_SECRET_KEY"
        )
    return {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}


def get_account() -> dict:
    """查詢帳戶狀態, 回傳 {"equity": 帳戶總淨值, "cash": 現金餘額}, 皆為 float"""
    response = requests.get(
        f"{_get_base_url()}/v2/account",
        headers=_build_authentication_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    account = response.json()
    return {"equity": float(account["equity"]), "cash": float(account["cash"])}


def get_positions() -> dict:
    """查詢目前持倉, 回傳 {股票代號: 股數}, 只含非零倉位"""
    response = requests.get(
        f"{_get_base_url()}/v2/positions",
        headers=_build_authentication_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    positions = response.json()
    return {position["symbol"]: float(position["qty"]) for position in positions}


def get_todays_calendar_entry(today: str) -> dict | None:
    """
    查詢指定日期(today, 格式 YYYY-MM-DD, 呼叫端應傳入美東時間的日期字串, 見 run_once_stocks.py)
    是否為交易日, 非交易日(週末/假日) 回傳 None
    """
    response = requests.get(
        f"{_get_base_url()}/v2/calendar",
        params={"start": today, "end": today},
        headers=_build_authentication_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    calendar_entries = response.json()
    return calendar_entries[0] if calendar_entries else None


def round_quantity_down_to_whole_shares(quantity: float) -> int:
    """把下單數量向下裁到整數股(本專案不支援分數股), 純函數, 可獨立單元測試"""
    return int(quantity)


def _submit_order(order_payload: dict) -> tuple[int, dict]:
    """對 /v2/orders 送出委託, 回傳 (HTTP 狀態碼, 交易所回應 JSON) , 不拋例外, 由呼叫端判斷成敗"""
    response = requests.post(
        f"{_get_base_url()}/v2/orders",
        json=order_payload,
        headers=_build_authentication_headers(),
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return response.status_code, response.json()


def place_limit_on_open_order(
    symbol: str, side: str, quantity: int, limit_price: float
) -> tuple[int, dict]:
    """下開盤限價單(limit-on-open, LOO): type=limit, time_in_force=opg, 交易所在次日開盤拍賣時撮合"""
    return _submit_order(
        {
            "symbol": symbol,
            "side": side.lower(),
            "type": "limit",
            "time_in_force": "opg",
            "qty": str(quantity),
            "limit_price": str(limit_price),
        }
    )


def place_market_on_open_order(symbol: str, side: str, quantity: int) -> tuple[int, dict]:
    """下開盤市價單(market-on-open, MOO): type=market, time_in_force=opg, 保證在開盤拍賣成交"""
    return _submit_order(
        {
            "symbol": symbol,
            "side": side.lower(),
            "type": "market",
            "time_in_force": "opg",
            "qty": str(quantity),
        }
    )
