"""
實驗生成器: 從 _template/config.py 蓋出一個新實驗資料夾, 保證每個實驗的 config.py 一致
用法: python new_experiment.py exp_003_rsi_filter   (省略名稱則啟動後由鍵盤輸入)

只複製範本, 不代填參數與假設; 生成後改 config.py 的參數, 再跑實驗.
notes.md, results.json 等產物由 run_experiment.py 首次執行時自動生成.
"""

import os
import shutil
import sys

_experiments_directory = os.path.dirname(os.path.abspath(__file__))
_template_config_path = os.path.join(_experiments_directory, "_template", "config.py")


def create_experiment(experiment_name: str) -> str:
    """建立新實驗資料夾並從範本複製 config.py, 回傳新資料夾路徑"""
    if not experiment_name:
        raise ValueError("必須提供實驗資料夾名稱")
    if os.sep in experiment_name or experiment_name.startswith("."):
        raise ValueError(f"實驗名稱不合法: {experiment_name}")

    experiment_directory = os.path.join(_experiments_directory, experiment_name)
    if os.path.exists(experiment_directory):
        raise FileExistsError(f"資料夾已存在, 不覆蓋: {experiment_directory}")
    if not os.path.exists(_template_config_path):
        raise FileNotFoundError(f"找不到範本 {_template_config_path}")

    os.makedirs(experiment_directory)
    shutil.copyfile(
        _template_config_path, os.path.join(experiment_directory, "config.py")
    )
    return experiment_directory


if __name__ == "__main__":
    # 啟動時有傳參就直接用, 沒有則等待鍵盤輸入
    experiment_name = sys.argv[1] if len(sys.argv) > 1 else None
    if experiment_name is None:
        experiment_name = input(
            "請輸入新實驗資料夾名稱 (例如 exp_003_rsi_filter): "
        ).strip()

    try:
        new_directory = create_experiment(experiment_name)
    except (ValueError, FileExistsError, FileNotFoundError) as error:
        sys.exit(f"錯誤: {error}")
    print(f"已建立 {new_directory}")
    print("下一步: 改 config.py 參數, 再執行 python config.py 跑實驗")
