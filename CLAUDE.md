# CLAUDE.md

Guidance for Claude Code in this repo.

## Meta

Everything written to CLAUDE.md must be short and direct.

## Writing

- English punctuation only (`.`, `,`, `!`, `?`, `:`, `;`, `()`), even in Chinese.
- In Chinese, put a space after each punctuation mark.
- Reply in whatever language the user's question is written in.
- Every specific term must include its original English term.
- Every abbreviation must be annotated with its full form.

Example: 這個策略基於趨勢跟蹤 (trend following) 原則, 使用 EMA (exponential moving average, 指數移動平均線) 雙均線作為入場信號. 樣本外 (out-of-sample, OOS) Sharpe > 1.0.

## Naming

- No abbreviations in variable names — full descriptive names. Readability over brevity.
- DataFrame column names follow the same rule (they appear in output).
- Every abbreviation in a comment needs its full form in parentheses on first use. Skip if already present.

## Commands

Install dependencies:

```bash
pip install -r requirements.txt
```

## Architecture

Monorepo, learning → live. Directories activate by phase in order — never build ahead.

| Directory | Purpose | Active Phase |
|---|---|---|
| `01_learning/` | Concept scripts — run and study, not imported | Pre-0, 1 |
| `02_data/` | Data fetchers (Binance Testnet, Alpaca Paper) | 2+ |
| `03_research/` | Indicators, strategy base class, backtest engine | 2 |
| `04_paper_trading/` | 4-agent paper trading system | 3 |
| `05_live/` | Live trading — do not touch until Phase 3 is complete | 4 |
| `tests/` | Unit tests for research layer | 2+ |
| `project_manage/` | ROADMAP, DECISIONS, STRATEGY_LOG — not code | Always |

Pandas:

- No `for` loops or `if-else` in signal/indicator logic — vectorize.
- `apply(lambda row: ...)` is last resort (10–100x slower).

## Git

- After any change, commit and push to the current branch. No confirmation needed.

## Research Workflow

- Log every experiment in `project_manage/STRATEGY_LOG.md`: hypothesis before code, conclusion after. Failed runs count.
- Research commit: `research: exp_XXX [strategy] - OOS Sharpe=X.X MaxDD=-XX%`
- Learning commit: `learn: [concept] - [one-line insight]`