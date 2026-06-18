"""
過擬合(Overfitting) 演示: 在同一份數據上測試大量參數組合, 一定能找到「看起來很棒」的組合,
但那往往只是運氣好(noise) , 不是策略真的有效. 這是回測最容易踩的陷阱之一
"""

import itertools
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

local_data_file_path = os.path.join(
    os.path.dirname(__file__), "data", "btc_usdt_daily.csv"
)
if not os.path.exists(local_data_file_path):
    raise FileNotFoundError(
        f"找不到 {local_data_file_path}, 請先執行 01_ohlcv_basics.py 產生本地數據"
    )
daily_kline_dataframe = pd.read_csv(local_data_file_path, parse_dates=["open_time"])
daily_return_percentage = daily_kline_dataframe["close"].pct_change()


def calculate_annualized_sharpe_ratio(fast_window, slow_window, price_return_series):
    """給定一組快慢線參數, 算出 EMA 雙均線策略在 price_return_series 這段期間的年化 Sharpe"""
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
        return np.nan
    return (
        strategy_daily_return_percentage.mean()
        / strategy_daily_return_percentage.std()
        * np.sqrt(365)
    )


# 窮舉一大批快慢線參數組合, 這就是研究者最常做但也最危險的事: 「試到一個 Sharpe 最高的就拿來用」
fast_window_options = [5, 8, 10, 12, 15, 18, 20, 25]
slow_window_options = [20, 26, 30, 40, 50, 60, 80, 100]
grid_search_results = [
    {
        "fast_window": fast_window,
        "slow_window": slow_window,
        "sharpe_ratio": calculate_annualized_sharpe_ratio(
            fast_window, slow_window, daily_return_percentage
        ),
    }
    for fast_window, slow_window in itertools.product(
        fast_window_options, slow_window_options
    )
    if fast_window < slow_window
]
grid_search_result_dataframe = pd.DataFrame(grid_search_results).dropna()
best_combination_in_sample = grid_search_result_dataframe.sort_values(
    "sharpe_ratio", ascending=False
).iloc[0]

# 把整批參數組合的 Sharpe 畫成熱力圖: 如果分布雜亂無章(高低交錯) , 代表表現好壞主要是噪音,
# 不是參數本身真的有規律的優勢, 這正是過擬合的視覺特徵
sharpe_pivot_table = grid_search_result_dataframe.pivot(
    index="slow_window", columns="fast_window", values="sharpe_ratio"
)
figure, heatmap_axes = plt.subplots(figsize=(10, 6))
heatmap_image = heatmap_axes.imshow(sharpe_pivot_table, cmap="RdYlGn", aspect="auto")
heatmap_axes.set_xticks(
    range(len(sharpe_pivot_table.columns)), sharpe_pivot_table.columns
)
heatmap_axes.set_yticks(range(len(sharpe_pivot_table.index)), sharpe_pivot_table.index)
heatmap_axes.set_xlabel("快線天數")
heatmap_axes.set_ylabel("慢線天數")
heatmap_axes.set_title("不同 EMA 參數組合的全樣本 Sharpe Ratio(顏色越綠越高)")
figure.colorbar(heatmap_image, label="Sharpe Ratio")
figure.tight_layout()
plt.show()

# 把全樣本選出來的「最佳」參數, 拆開放到前 70% 和後 30% 分別重新計算 Sharpe,
# 如果這組參數真的有效, 前後段表現應該接近; 如果差很多, 就是過擬合到了特定那段歷史的噪音
split_index_position = int(len(daily_return_percentage) * 0.7)
first_part_sharpe = calculate_annualized_sharpe_ratio(
    int(best_combination_in_sample["fast_window"]),
    int(best_combination_in_sample["slow_window"]),
    daily_return_percentage.iloc[:split_index_position],
)
second_part_sharpe = calculate_annualized_sharpe_ratio(
    int(best_combination_in_sample["fast_window"]),
    int(best_combination_in_sample["slow_window"]),
    daily_return_percentage.iloc[split_index_position:],
)

print(f"測試過 {len(grid_search_result_dataframe)} 組參數組合")
print(
    f"全樣本最佳組合: 快線 {int(best_combination_in_sample['fast_window'])} 日, "
    f"慢線 {int(best_combination_in_sample['slow_window'])} 日, "
    f"全樣本 Sharpe={best_combination_in_sample['sharpe_ratio']:.2f}"
)
print(f"同一組參數在前 70% 資料的 Sharpe: {first_part_sharpe:.2f}")
print(f"同一組參數在後 30% 資料的 Sharpe: {second_part_sharpe:.2f}")
print(
    "如果兩段差距很大, 代表「全樣本最佳」只是過擬合到特定歷史路徑的噪音, 而不是真正穩定的優勢"
)
