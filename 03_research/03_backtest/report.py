"""
回測報告輸出 — 把 BacktestResult 存成標準化的 JSON 績效報告與淨值曲線圖
對應 ROADMAP「標準化輸出: JSON 格式績效報告 + 淨值曲線圖」與每次實驗保存 results.json 的工作流
"""

import json
import os

import matplotlib

# 使用非互動式後端, 讓報告在無圖形介面的伺服器上也能存圖
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 設定中文字體, 避免圖表上的中文文字顯示成方框
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK TC", "WenQuanYi Zen Hei"]
plt.rcParams["axes.unicode_minus"] = False


def save_equity_curve_image(equity_curve, output_file_path: str, title: str) -> None:
    """把淨值曲線畫成 PNG 存檔, 直觀檢視策略是否穩定向上成長"""
    figure, equity_axes = plt.subplots(figsize=(12, 5))
    equity_axes.plot(equity_curve.values, color="seagreen")
    equity_axes.set_ylabel("賬戶淨值(美元)")
    equity_axes.set_xlabel("交易日序號")
    equity_axes.set_title(title)
    figure.tight_layout()
    figure.savefig(output_file_path)
    plt.close(figure)


def save_report(
    backtest_result,
    output_directory: str,
    strategy_name: str,
    strategy_parameters: dict,
    dataset_name: str = "",
) -> None:
    """
    把一次回測結果存成 results.json(績效指標 + 策略參數) 與 equity_curve.png
    參數 output_directory: 通常是 experiments/exp_XXX/ 目錄
    """
    os.makedirs(output_directory, exist_ok=True)

    report_content = {
        "strategy_name": strategy_name,
        "dataset_name": dataset_name,
        "strategy_parameters": strategy_parameters,
        "initial_capital": backtest_result.initial_capital,
        "final_equity": float(backtest_result.equity_curve.iloc[-1]),
        "metrics": backtest_result.metrics,
    }
    results_json_path = os.path.join(output_directory, "results.json")
    with open(results_json_path, "w", encoding="utf-8") as results_file:
        json.dump(report_content, results_file, ensure_ascii=False, indent=2)

    equity_curve_image_path = os.path.join(output_directory, "equity_curve.png")
    save_equity_curve_image(
        backtest_result.equity_curve,
        equity_curve_image_path,
        f"{strategy_name} {dataset_name} 淨值曲線".strip(),
    )

    # 逐筆交易明細另存 CSV, 供 ROADMAP 要求的手動核對至少 10 筆交易
    trades_csv_path = os.path.join(output_directory, "trades.csv")
    backtest_result.trades.to_csv(trades_csv_path, index=False)
