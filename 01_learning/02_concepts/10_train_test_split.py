"""
樣本內外劃分(Train/Test Split) 與 Walk-Forward 驗證: 正式的研究方法論,
之後 Phase 2 所有實驗都要遵守 — 樣本外的數據絕對不能拿來調參, 只能用一次做最終驗證
時間序列資料不能隨機打亂分割, 必須按時間順序切, 否則等於讓模型看到未來(前視偏差的另一種形式)
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# 設定中文字體, 避免圖表上的中文文字顯示成方框
plt.rcParams["font.sans-serif"] = ["Noto Sans CJK TC", "WenQuanYi Zen Hei"]
plt.rcParams["axes.unicode_minus"] = False

local_data_file_path = os.path.join(
    os.path.dirname(__file__), "data", "btc_usdt_daily.csv"
)
if not os.path.exists(local_data_file_path):
    raise FileNotFoundError(
        f"找不到 {local_data_file_path}, 請先執行 01_ohlcv_basics.py 產生本地數據"
    )
daily_kline_dataframe = pd.read_csv(local_data_file_path, parse_dates=["open_time"])
daily_return_percentage = daily_kline_dataframe["close"].pct_change()
candidate_fast_windows = [8, 12, 15, 20]
candidate_slow_windows = [26, 40, 60, 80]


def calculate_annualized_sharpe_ratio(fast_window, slow_window, price_return_series):
    """給定一組快慢線參數, 算出 EMA 策略在 price_return_series 這段期間的年化 Sharpe"""
    exponential_moving_average_fast = (
        daily_kline_dataframe["close"].ewm(span=fast_window, adjust=False).mean()
    )
    exponential_moving_average_slow = (
        daily_kline_dataframe["close"].ewm(span=slow_window, adjust=False).mean()
    )
    executed_position = (
        (exponential_moving_average_fast > exponential_moving_average_slow)
        .astype(int)
        .shift(1)
    )
    strategy_daily_return_percentage = (
        executed_position * price_return_series
    ).reindex(price_return_series.index)
    if (
        strategy_daily_return_percentage.std() == 0
        or strategy_daily_return_percentage.dropna().empty
    ):
        return np.nan, (fast_window, slow_window)
    return (
        strategy_daily_return_percentage.mean()
        / strategy_daily_return_percentage.std()
        * np.sqrt(365),
        (fast_window, slow_window),
    )


def find_best_combination_on_training_data(training_return_series):
    """只用訓練期間的數據選參數, 模擬研究時「只能看過去, 不能偷看未來」的真實限制"""
    all_results = [
        calculate_annualized_sharpe_ratio(
            fast_window, slow_window, training_return_series
        )
        for fast_window in candidate_fast_windows
        for slow_window in candidate_slow_windows
    ]
    valid_results = [result for result in all_results if not np.isnan(result[0])]
    return max(valid_results, key=lambda result: result[0])


# 第一部分: 標準 70/30 切分 — 前 70% 是樣本內(訓練/調參用) , 後 30% 是樣本外(只驗證一次, 不能回頭調參)
split_index_position = int(len(daily_return_percentage) * 0.7)
in_sample_returns = daily_return_percentage.iloc[:split_index_position]
out_of_sample_returns = daily_return_percentage.iloc[split_index_position:]
in_sample_best_sharpe, in_sample_best_combination = (
    find_best_combination_on_training_data(in_sample_returns)
)
out_of_sample_sharpe, _ = calculate_annualized_sharpe_ratio(
    *in_sample_best_combination, out_of_sample_returns
)

print(
    f"樣本內(前 70%) 選出最佳參數: 快線 {in_sample_best_combination[0]} 日, "
    f"慢線 {in_sample_best_combination[1]} 日, 樣本內 Sharpe={in_sample_best_sharpe:.2f}"
)
print(f"同一組參數在樣本外(後 30%) 的 Sharpe={out_of_sample_sharpe:.2f}(只驗證這一次)")

# 第二部分: Walk-Forward 驗證 — 把資料切成 4 段, 每一段測試前都只用「這段之前」的數據重新選參數,
# 模擬真實研究流程隨著時間推進不斷往前滾動, 而不是一次性切一刀就結束
fold_boundary_positions = np.linspace(0, len(daily_return_percentage), 5, dtype=int)
walk_forward_fold_results = []
for fold_index in range(1, 4):
    expanding_training_returns = daily_return_percentage.iloc[
        : fold_boundary_positions[fold_index]
    ]
    testing_returns = daily_return_percentage.iloc[
        fold_boundary_positions[fold_index] : fold_boundary_positions[fold_index + 1]
    ]
    _, best_combination_for_this_fold = find_best_combination_on_training_data(
        expanding_training_returns
    )
    fold_test_sharpe, _ = calculate_annualized_sharpe_ratio(
        *best_combination_for_this_fold, testing_returns
    )
    walk_forward_fold_results.append(
        {"fold": f"第 {fold_index + 1} 段", "sharpe_ratio": fold_test_sharpe}
    )
walk_forward_result_dataframe = pd.DataFrame(walk_forward_fold_results)

figure, fold_axes = plt.subplots(figsize=(10, 5))
fold_axes.bar(
    walk_forward_result_dataframe["fold"],
    walk_forward_result_dataframe["sharpe_ratio"],
    color="steelblue",
)
fold_axes.axhline(0, color="gray", linewidth=0.8)
fold_axes.set_ylabel("樣本外 Sharpe Ratio")
fold_axes.set_title("Walk-Forward 驗證: 每段測試前都只用該段之前的數據重新選參數")
figure.tight_layout()
images_output_directory_path = os.path.join(os.path.dirname(__file__), ".images")
os.makedirs(images_output_directory_path, exist_ok=True)
figure.savefig(os.path.join(images_output_directory_path, "10_train_test_split.png"))
plt.show()

print("Walk-Forward 各段樣本外表現:")
print(walk_forward_result_dataframe.to_string(index=False))
print(
    "如果各段表現忽好忽壞, 代表這個策略沒有穩定的優勢, 過去調出來的好參數不保證未來繼續有效"
)
