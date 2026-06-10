# Quant Trading System

> 唯一的事實來源: 系統當前狀態

## 當前階段

**Phase 0 — 環境建設**

- [ ] Repo 結構建立完成
- [ ] `.env` 填好 API Key, 已在 `.gitignore` 中
- [ ] Binance Testnet API 調用成功
- [ ] Alpaca Paper API 調用成功
- [ ] 第一個 commit 推送到 GitHub

## 目錄說明

| 目錄 | 用途 | 激活階段 |
|------|------|----------|
| `01_learning/` | 10 個概念學習腳本 | Phase 1 |
| `02_data/` | 數據拉取與緩存 | Phase 2+ |
| `03_research/` | 策略研究與回測 | Phase 2 |
| `04_paper_trading/` | 自動化 Paper Trading | Phase 3 |
| `05_live/` | 實盤(Phase 3 完成後才動) | Phase 4 |
| `tests/` | 單元測試 | Phase 2+ |

## 重要文件

- `STRATEGY_LOG.md` — 每次策略實驗的研究日誌(最重要)
- `DECISIONS.md` — 架構決策記錄
- `.env.example` — API Key 佔位符模板
