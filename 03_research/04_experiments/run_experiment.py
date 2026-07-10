"""
實驗執行器: 統一跑一個實驗資料夾的回測, 讓每次實驗只需一行指令
用法: python run_experiment.py exp_001_ema_baseline

流程: 讀該實驗資料夾的 config.py, 載入數據, 建策略與引擎, 跑 70/30 樣本內外分割回測,
     再寫出 results.json(樣本內外指標) , 樣本內外淨值曲線圖, 逐筆交易 CSV, 以及 notes.md 骨架
假設(hypothesis) 與結論(conclusion) 由你在 notes.md 與 STRATEGY_LOG.md 手寫, 執行器不代寫.
"""

import argparse
import importlib.util
import json
import os
import sys

import pandas as pd

_experiments_directory = os.path.dirname(os.path.abspath(__file__))
_research_directory = os.path.dirname(_experiments_directory)
_repository_root = os.path.dirname(_research_directory)
# 目錄名以數字開頭無法當成 Python 套件, 手動把指標層, 策略層, 回測層加入模組搜尋路徑
for _module_subdirectory in ["01_indicators", "02_strategies", "03_backtest"]:
    sys.path.insert(0, os.path.join(_research_directory, _module_subdirectory))
from engine import BacktestEngine  # noqa: E402
from report import save_equity_curve_image  # noqa: E402
from trend_following import TrendFollowingStrategy  # noqa: E402

# 策略名稱到策略類別的對照表, 新增策略時在此登記
STRATEGY_REGISTRY = {
    "trend_following": TrendFollowingStrategy,
}


def load_experiment_config(experiment_name: str):
    """動態載入某實驗資料夾裡的 config.py 模組"""
    config_file_path = os.path.join(
        _experiments_directory, experiment_name, "config.py"
    )
    if not os.path.exists(config_file_path):
        raise FileNotFoundError(f"找不到 {config_file_path}")
    module_specification = importlib.util.spec_from_file_location(
        f"{experiment_name}_config", config_file_path
    )
    config_module = importlib.util.module_from_spec(module_specification)
    module_specification.loader.exec_module(config_module)
    return config_module


def load_dataset(dataset_file_name: str) -> pd.DataFrame:
    """從 02_data/cache 載入研究用的 OHLCV 數據"""
    dataset_path = os.path.join(_repository_root, "02_data", "cache", dataset_file_name)
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(
            f"找不到數據 {dataset_path}, 請先執行 02_data/fetchers 抓取"
        )
    return pd.read_csv(dataset_path, parse_dates=["open_time"])


def run_experiment(experiment_name: str) -> dict:
    """跑完整實驗並把所有產物寫回實驗資料夾, 回傳彙總的 results 字典"""
    config = load_experiment_config(experiment_name)
    ohlcv_dataframe = load_dataset(config.DATASET)

    strategy_class = STRATEGY_REGISTRY[config.STRATEGY]
    strategy = strategy_class(**config.STRATEGY_PARAMS)
    engine = BacktestEngine(**config.ENGINE_PARAMS)

    # 樣本內調參, 樣本外驗證; 樣本外數字才算數
    in_sample_result, out_of_sample_result = engine.run_with_split(
        ohlcv_dataframe, strategy, config.IN_SAMPLE_RATIO
    )

    output_directory = os.path.join(_experiments_directory, experiment_name)
    results = {
        "experiment_name": experiment_name,
        "dataset": config.DATASET,
        "strategy": config.STRATEGY,
        "strategy_parameters": strategy.describe_parameters(),
        "engine_parameters": config.ENGINE_PARAMS,
        "in_sample_ratio": config.IN_SAMPLE_RATIO,
        "in_sample_metrics": in_sample_result.metrics,
        "out_of_sample_metrics": out_of_sample_result.metrics,
    }
    with open(
        os.path.join(output_directory, "results.json"), "w", encoding="utf-8"
    ) as results_file:
        json.dump(results, results_file, ensure_ascii=False, indent=2)

    # 樣本內外各存一張淨值曲線圖, 直觀對比兩段表現是否一致(不一致代表策略不穩)
    save_equity_curve_image(
        in_sample_result.equity_curve,
        os.path.join(output_directory, "equity_curve_in_sample.png"),
        f"{experiment_name} 樣本內淨值曲線",
    )
    save_equity_curve_image(
        out_of_sample_result.equity_curve,
        os.path.join(output_directory, "equity_curve_out_of_sample.png"),
        f"{experiment_name} 樣本外淨值曲線",
    )
    out_of_sample_result.trades.to_csv(
        os.path.join(output_directory, "trades_out_of_sample.csv"), index=False
    )

    _write_notes_skeleton(output_directory, experiment_name, results)
    return results


def _format_metrics_table(in_sample_metrics: dict, out_of_sample_metrics: dict) -> str:
    """把樣本內外指標排成一張 Markdown 表格, 方便肉眼對比兩段是否一致"""
    metric_labels = {
        "compound_annual_growth_rate": "年化報酬 (CAGR)",
        "annualized_sharpe_ratio": "Sharpe",
        "maximum_drawdown": "最大回撤",
        "win_rate": "勝率",
        "profit_factor": "盈虧比",
        "number_of_trades": "交易筆數",
    }
    lines = ["| 指標 | 樣本內 | 樣本外 |", "| --- | --- | --- |"]
    for metric_key, label in metric_labels.items():
        in_sample_value = in_sample_metrics[metric_key]
        out_of_sample_value = out_of_sample_metrics[metric_key]
        if metric_key == "number_of_trades":
            lines.append(f"| {label} | {in_sample_value} | {out_of_sample_value} |")
        elif metric_key in ("annualized_sharpe_ratio", "profit_factor"):
            lines.append(
                f"| {label} | {in_sample_value:.2f} | {out_of_sample_value:.2f} |"
            )
        else:
            lines.append(
                f"| {label} | {in_sample_value:.1%} | {out_of_sample_value:.1%} |"
            )
    return "\n".join(lines)


def _write_notes_skeleton(
    output_directory: str, experiment_name: str, results: dict
) -> None:
    """
    產生 notes.md 骨架: 自動填好結果表格, 假設與結論留白給你手寫
    若 notes.md 已存在則不覆蓋, 避免蓋掉你寫過的假設與結論
    """
    notes_path = os.path.join(output_directory, "notes.md")
    if os.path.exists(notes_path) and os.path.getsize(notes_path) > 0:
        return
    metrics_table = _format_metrics_table(
        results["in_sample_metrics"], results["out_of_sample_metrics"]
    )
    notes_content = f"""# {experiment_name}

## 假設 (執行前手寫)

<!-- 一兩句話: 你預期什麼, 為什麼. 先寫這裡, 再跑實驗. -->

## 實驗設置

- 數據: {results['dataset']}
- 策略: {results['strategy']}
- 參數: {results['strategy_parameters']}
- 樣本內比例: {results['in_sample_ratio']}

## 結果 (執行器自動填)

{metrics_table}

## 結論 (執行後手寫)

<!-- 假設成立嗎? 為什麼? 樣本內外差異說明什麼? 失敗的結論同樣有價值. -->

## 下一步

<!-- 下一個要驗證的假設. -->
"""
    with open(notes_path, "w", encoding="utf-8") as notes_file:
        notes_file.write(notes_content)


def run_and_print_summary(experiment_name: str) -> dict:
    """跑實驗並印出樣本外摘要; 供命令列與各 config.py 直接執行共用"""
    experiment_results = run_experiment(experiment_name)
    out_of_sample = experiment_results["out_of_sample_metrics"]
    print(f"實驗 {experiment_name} 完成, 產物已寫回資料夾")
    print(
        f"樣本外: Sharpe={out_of_sample['annualized_sharpe_ratio']:.2f}, "
        f"最大回撤={out_of_sample['maximum_drawdown']:.1%}, "
        f"交易筆數={out_of_sample['number_of_trades']}"
    )
    return experiment_results


if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser(description="跑一個實驗資料夾的回測")
    argument_parser.add_argument(
        "experiment_name",
        nargs="?",
        default=None,
        help="實驗資料夾名稱, 例如 exp_001_ema_baseline; 省略則啟動後由鍵盤輸入",
    )
    parsed_arguments = argument_parser.parse_args()

    # 啟動時有傳參就直接用, 沒有則等待鍵盤輸入
    experiment_name = parsed_arguments.experiment_name
    if experiment_name is None:
        experiment_name = input("請輸入實驗資料夾名稱 (例如 exp_001_ema_baseline): ").strip()
    if not experiment_name:
        argument_parser.error("必須提供實驗資料夾名稱")

    run_and_print_summary(experiment_name)
