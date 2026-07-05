"""
動量指標庫 — 衡量價格漲跌動能與速度的向量化指標函數
所有函數只依賴 pandas, 全部向量化, 無 for loop, 無逐列 if-else
"""

import pandas as pd


def relative_strength_index(close_price: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI(Relative Strength Index, 相對強弱指標) — 衡量近期漲勢相對跌勢的強度, 範圍 0 到 100
    常見解讀: RSI > 70 代表超買(overbought) , RSI < 30 代表超賣(oversold)
    用威爾德平滑(Wilder Smoothing, alpha=1/period 的 EMA) 分別平滑上漲幅度與下跌幅度
    """
    price_change = close_price.diff()
    # 把每日價格變動拆成純上漲幅度與純下跌幅度(下跌幅度取正值) , 用 clip 取代逐列 if-else
    upward_change = price_change.clip(lower=0)
    downward_change = (-price_change).clip(lower=0)

    wilder_smoothing_alpha = 1 / period
    average_upward_change = upward_change.ewm(
        alpha=wilder_smoothing_alpha, adjust=False
    ).mean()
    average_downward_change = downward_change.ewm(
        alpha=wilder_smoothing_alpha, adjust=False
    ).mean()

    # RS(Relative Strength, 相對強度) = 平均漲幅 / 平均跌幅, RSI 再把它壓縮到 0 到 100 區間
    relative_strength = average_upward_change / average_downward_change
    return 100 - 100 / (1 + relative_strength)


def rate_of_change(close_price: pd.Series, period: int = 10) -> pd.Series:
    """
    ROC(Rate of Change, 變動率) — 收盤價相對 period 天前的漲跌百分比, 最直接的動量衡量
    正值代表上漲動能, 負值代表下跌動能, 絕對值越大代表動能越強
    """
    return close_price.pct_change(periods=period)


def moving_average_convergence_divergence(
    close_price: pd.Series,
    fast_span: int = 12,
    slow_span: int = 26,
    signal_span: int = 9,
) -> pd.DataFrame:
    """
    MACD(Moving Average Convergence Divergence, 指數平滑異同移動平均線) — 快慢 EMA 之差衡量趨勢動能
    回傳三欄: macd_line(快慢線差) , signal_line(macd 的 EMA) , histogram(兩者之差)
    histogram 由負轉正常被視為多頭動能增強, 由正轉負常被視為空頭動能增強
    """
    exponential_moving_average_fast = close_price.ewm(span=fast_span, adjust=False).mean()
    exponential_moving_average_slow = close_price.ewm(span=slow_span, adjust=False).mean()
    macd_line = exponential_moving_average_fast - exponential_moving_average_slow
    signal_line = macd_line.ewm(span=signal_span, adjust=False).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame(
        {
            "macd_line": macd_line,
            "signal_line": signal_line,
            "histogram": histogram,
        }
    )
