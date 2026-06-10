# 數據字典

## Fetchers

| 文件 | 數據源 | 用途 |
|------|--------|------|
| `fetchers/binance_fetcher.py` | Binance REST API | 加密貨幣歷史 K 線, 存本地 cache |
| `fetchers/alpaca_fetcher.py` | Alpaca Markets API | 美股歷史日線(調整後價格) |

## Cache 目錄

`cache/` 目錄由 `.gitignore` 排除, 本地緩存數據以避免重複拉取.

支持的格式: `.csv`, `.parquet`, `.h5`(均被 gitignore)

## 數據字段說明

OHLCV 標準格式:

| 字段 | 含義 |
|------|------|
| `open` | 開盤價 |
| `high` | 最高價 |
| `low` | 最低價 |
| `close` | 收盤價 |
| `volume` | 成交量 |
| `timestamp` | UTC 時間戳 |
