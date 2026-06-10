# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Writing Rules

Regardless of language used (English or Chinese), always use English punctuation marks (`.`, `,`, `!`, `?`, `:`, `;`, `()`). When writing Chinese text with English punctuation, follow each punctuation mark with a space.

Example: 這個策略基於趨勢跟蹤原則, 使用 EMA 雙均線作為入場信號. 回測數據顯示樣本外 Sharpe > 1.0.

## Commands

Run a single learning/research script:

Install dependencies:

```bash
pip install -r requirements.txt
```

## Architecture

This is a monorepo covering the full lifecycle from learning to live trading. Directories activate sequentially by phase — do not build ahead of the current phase.

**Phase progression:**

| Directory | Purpose | Active Phase |
|---|---|---|
| `01_learning/` | Concept scripts — run and study directly, not imported | Pre-Phase 0, Phase 1 |
| `02_data/` | Market data fetchers (Binance Testnet, Alpaca Paper) | Phase 2+ |
| `03_research/` | Indicator library, strategy base class, backtest engine | Phase 2 |
| `04_paper_trading/` | 4-agent automated paper trading system | Phase 3 |
| `05_live/` | Live trading — **do not touch until Phase 3 is complete** | Phase 4 |
| `tests/` | Unit tests for research-layer components | Phase 2+ |
| `project_manage/` | ROADMAP, DECISIONS, STRATEGY_LOG — not code | Always |

**Pandas convention:**

- Zero `for` loops, zero `if-else` in signal/indicator logic — vectorize everything.
- `apply(lambda row: ...)` is a last resort; it is 10–100x slower than vectorized operations.

## Research Workflow

Every strategy experiment goes in `project_manage/STRATEGY_LOG.md` — write the hypothesis before touching code, record the conclusion after (failed experiments are equally valuable). Commit format: `research: exp_XXX [strategy name] - OOS Sharpe=X.X MaxDD=-XX%`.

Learning script commit format: `learn: [concept] - [one-line key insight]`.
