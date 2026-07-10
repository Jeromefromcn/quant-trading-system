"""
策略基類: 所有交易策略的共同介面
一個策略的唯一職責: 吃進一份 OHLCV(開高低收量) 數據, 吐出每天的目標倉位信號
倉位信號約定: 1 代表持有多單(long) , 0 代表空手(flat) , 不在信號層做前視偏差處理與倉位大小計算,
那是回測引擎(engine) 的職責, 策略只負責回答這一天我想不想持有
"""

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """交易策略抽象基類, 子類必須實作 generate_signals"""

    #: 供日誌與報告使用的策略名稱, 子類應覆寫
    name: str = "unnamed_strategy"

    @abstractmethod
    def generate_signals(self, ohlcv_dataframe: pd.DataFrame) -> pd.Series:
        """
        根據輸入的 OHLCV 數據產生每天的目標倉位信號
        參數 ohlcv_dataframe 至少需包含 open, high, low, close, volume 欄位
        回傳一個與輸入等長的 Series, 值為 1(持有多單) 或 0(空手) , 索引與輸入對齊
        重點: 此處回傳的是當天收盤後決定的目標倉位, 不做 shift, 由回測引擎統一位移以避免前視偏差
        """
        raise NotImplementedError

    def describe_parameters(self) -> dict:
        """回傳策略的參數字典, 供實驗記錄與報告輸出使用, 子類可覆寫以列出自己的參數"""
        return {}
