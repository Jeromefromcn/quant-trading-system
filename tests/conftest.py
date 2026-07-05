"""
pytest 共用設定 — 把 03_research 下以數字開頭(無法當 Python 套件) 的模組目錄加入搜尋路徑
讓測試能直接 import volatility, trend, momentum, base, trend_following, engine, metrics, report
"""

import os
import sys

_repository_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_research_module_directories = [
    os.path.join(_repository_root, "03_research", "01_indicators"),
    os.path.join(_repository_root, "03_research", "02_strategies"),
    os.path.join(_repository_root, "03_research", "03_backtest"),
]
for _module_directory in _research_module_directories:
    if _module_directory not in sys.path:
        sys.path.insert(0, _module_directory)
