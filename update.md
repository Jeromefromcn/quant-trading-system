# HTML 修改計劃：為未來 Agent 研究迴圈補充結構化字段

## 背景

原有路線圖的 Phase 2 實驗記錄格式是為**人類閱讀**設計的（自然語言假設、無機器可解析的 edge 分類）。
本次修改補充 3 個結構化字段，讓 Phase 2 累積的實驗記錄對未來的 AI agent 研究迴圈是可讀的、可學習的。

**目標文件：** `quant_trading_roadmap.html`
**修改範圍：** 只動 `<section id="phase2">` 內的內容，其他 section 不碰。
**修改數量：** 4 處，順序執行。

---

## 修改 1：在 STRATEGY_LOG 模板之前，新增 config.py 結構化假設格式

### 定位

在 `<section id="phase2">` 內，找到以下 `<h3>` 標籤：

```html
<h3>STRATEGY_LOG.md 標準模板</h3>
```

在這個 `<h3>` 標籤**之前**（緊靠它，中間不插空行）插入以下完整 HTML 片段。

### 插入內容

```html
<h3>實驗 config.py：結構化假設格式（Agent 可讀）</h3>
<p>每個 <code>experiments/exp_XXX/</code> 文件夾放一個 <code>config.py</code>。<code>HYPOTHESIS</code> 字典的字段是為未來 agent 研究迴圈設計的——這讓 agent 能從 30 個實驗裡學習「哪類機制在哪種市場環境下有效」，而不是盲目搜索參數空間。</p>
<pre><code># config.py 示例

HYPOTHESIS = {
    "statement":          "ADX 過濾能減少震盪市假信號，提升信號質量",
    "mechanism":          "ADX 測量趨勢強度，ADX&lt;25 代表市場無方向性，此時 EMA 交叉信號是噪聲而非真實趨勢",
    "edge_category":      "behavioral",   # behavioral / structural / risk_premium
    "failure_conditions": "趨勢突然反轉時 ADX 有滯後，可能造成晚出場；超低波動期 ADX 長期&lt;25，策略無交易",
    "inspired_by":        "exp_001 結論：樣本外假信號比例過高，震盪市表現拖累整體績效"
}
# edge_category 說明：
#   behavioral    = 市場參與者行為偏差造成的低效（情緒、羊群效應）
#   structural    = 市場結構性因素（流動性差異、機構限制）
#   risk_premium  = 承擔特定風險的補償（波動率、尾部風險）

BACKTEST_CONFIG = {
    "assets":         ["BTC/USDT", "ETH/USDT"],
    "timeframe":      "1d",
    "in_sample":      ("2020-01-01", "2023-06-30"),
    "out_sample":     ("2023-07-01", "2024-12-31"),
    "commission":     0.001,
    "slippage":       0.0005,
    "risk_per_trade": 0.015,
    "params": {
        "ema_fast":        20,
        "ema_slow":        50,
        "atr_mult":        2.0,
        "adx_threshold":   25
    }
}</code></pre>
```

---

## 修改 2：替換 STRATEGY_LOG.md 標準模板的 `<pre><code>` 內容

### 定位

在 `<section id="phase2">` 內，找到 `<h3>STRATEGY_LOG.md 標準模板</h3>` 之後緊跟著的 `<pre><code>` 塊。

這個塊的**開頭**是（用這行作為唯一定位錨點）：

```
## [YYYY-MM-DD] 實驗 #XXX：[一句話描述假設]
```

**將整個 `<pre><code>...</code></pre>` 塊（從 `<pre>` 到 `</pre>`）替換**為以下內容：

### 替換內容

```html
<pre><code>## [YYYY-MM-DD] 實驗 #XXX：[一句話描述假設]

### 假設（Statement）
[你在驗證什麼，用一句話說清楚]

### Edge 機制（Mechanism）
[為什麼這個邏輯應該成立？背後的市場行為假設是什麼？]
例：加密市場散戶佔比高，信息消化慢，趨勢慣性比成熟市場更顯著

### Edge 類型（Category）
behavioral | structural | risk_premium

### 失效條件（Failure Conditions）
[這個 edge 在什麼情況下會消失？什麼樣的市場結構變化會讓它失效？]
例：加密市場完全機構化後，趨勢跟蹤的結構性優勢預期會降低

### 實驗設置
- 資產：BTC/USDT, ETH/USDT
- 時間框架：日線
- 樣本內：2020-01-01 → 2023-06-30
- 樣本外：2023-07-01 → 2024-12-31
- 關鍵參數：EMA_fast=20, EMA_slow=50, ATR_mult=2.0, ADX_threshold=25

### 市場環境標籤（供 agent 解析）
- 樣本內：trending_bull / trending_bear / ranging / high_vol / low_vol（可多選）
- 樣本外：trending_bull / trending_bear / ranging / high_vol / low_vol（可多選）

### 結果
|          | 樣本內 | 樣本外 |
|----------|--------|--------|
| 年化收益 | +28%   | +11%   |
| 最大回撤 | -16%   | -24%   |
| Sharpe   | 1.3    | 0.7    |
| 勝率     | 42%    | 39%    |
| 盈虧比   | 2.1    | 1.8    |

### 結論
[樣本外 Sharpe 下降顯著，疑似輕度過擬合。ADX 過濾方向正確但不夠]

### Edge 是否得到支撐
[是 / 部分 / 否]  原因：[一句話，回答「為什麼這次結果支撐或否定了最初的機制假設」]

### 下一步實驗
[#XXX+1：調整 ATR 止損倍數，測試 1.5x / 2.0x / 2.5x 對回撤的影響]</code></pre>
```

---

## 修改 3：在 STRATEGY_LOG 模板之後，新增 results.json 擴展格式

### 定位

找到修改 2 中替換完成的 `</pre>` 結束標籤（STRATEGY_LOG 模板的那個 `</pre>`）。
在這個 `</pre>` **之後**（緊靠它）插入以下完整 HTML 片段。

### 插入內容

```html
<h3>results.json 擴展格式（含 Agent 可讀字段）</h3>
<p>回測引擎的標準化輸出格式。<code>edge_category</code>、<code>period_characteristics</code>、<code>edge_supported</code> 這三個字段是給未來 agent 解析用的，人工填寫時保持和 <code>config.py</code> 的 <code>HYPOTHESIS</code> 一致。</p>
<pre><code>{
  "experiment_id": "exp_002",
  "hypothesis_statement": "ADX 過濾能減少震盪市假信號",
  "edge_category": "behavioral",

  "period_characteristics": {
    "in_sample":  ["trending_bull", "high_volatility"],
    "out_sample": ["ranging", "low_volatility"]
  },

  "metrics": {
    "in_sample": {
      "annual_return":  0.28,
      "max_drawdown":  -0.16,
      "sharpe":         1.3,
      "win_rate":       0.42,
      "profit_factor":  2.1,
      "trade_count":    47
    },
    "out_sample": {
      "annual_return":  0.11,
      "max_drawdown":  -0.24,
      "sharpe":         0.7,
      "win_rate":       0.39,
      "profit_factor":  1.8,
      "trade_count":    19
    }
  },

  "oos_decay_ratio": 0.54,
  "edge_supported": "partial",
  "edge_supported_reason": "ADX 過濾在趨勢市有效，但樣本外恰為震盪市，結論受市場環境影響，需在不同環境再驗證"
}</code></pre>
```

---

## 修改 4：在 Phase 2 完成標準之前，新增 agent 說明 callout

### 定位

在 `<section id="phase2">` 內，找到 class 為 `crit amber` 的 `<div>`（這是「Phase 2 完成標準」的綠色框）：

```html
<div class="crit amber">
```

在這個 `<div class="crit amber">` **之前**（緊靠它）插入以下完整 HTML 片段。

### 插入內容

```html
<div class="co info">
  <span class="co-ic">🤖</span>
  <div>
    <strong>為什麼要加這些結構化字段？</strong><br>
    <code>Mechanism</code>、<code>Edge 類型</code>、<code>市場環境標籤</code>、<code>Edge 是否得到支撐</code> 這幾個字段現在看起來是多餘的——人工研究時你自然知道這些。它們的目的是：當你做完 30+ 個實驗之後，未來的 AI agent 可以解析這些結構化字段，學習「哪類機制在哪種市場環境下有效」，從而提出有根據的下一個假設。自然語言結論 agent 讀不懂；<code>edge_category: "behavioral"</code> + <code>out_sample: ["ranging"]</code> + <code>edge_supported: "partial"</code> agent 可以跨實驗比較和推理。
  </div>
</div>
```

---

## 執行順序與注意事項

1. **按 1 → 2 → 3 → 4 的順序執行**，因為修改 2、3 依賴修改 1 插入之後的 DOM 結構作為相對定位。
2. **`<pre><code>` 塊內的 HTML 特殊字符：** `<` 應寫為 `&lt;`，`>` 應寫為 `&gt;`。計劃中已在需要的地方標注（如 `ADX&lt;25`）。其他代碼塊內容無需額外轉義。
3. **不修改任何其他 section**（`#phase0`, `#phase1`, `#phase3`, `#phase4`, `#guardrails`, `#quickref`）。
4. 修改完成後，在瀏覽器打開 HTML 文件，確認 Phase 2 的視覺結構沒有錯位，代碼塊可正常顯示即完成。

---

## 修改後 Phase 2 的內容順序（供核對）

修改完成後，`<section id="phase2">` 內的 `<h3>` 順序應為：

1. 首先：搭建回測引擎（Phase 2 第一週）
2. 實驗工作流（每次實驗重複）
3. **[新增] 實驗 config.py：結構化假設格式（Agent 可讀）**
4. STRATEGY_LOG.md 標準模板（**已更新內容**）
5. **[新增] results.json 擴展格式（含 Agent 可讀字段）**
6. 研究推進序列（建議順序）
7. **[新增] agent callout**
8. Phase 2 完成標準（crit amber 框）