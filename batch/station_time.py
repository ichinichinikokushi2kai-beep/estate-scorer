"""
所要時間マスタ（station_time.xlsx）の読み込み。
列: 駅名 or 最寄り駅, 職場まで所要時間(分) or 所要時間 など「分」を含む列。
"""
import logging
from pathlib import Path
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


def load_station_time_master(path: str) -> Dict[str, int]:
    """
    station_time.xlsx を読み、{駅名: 所要時間(分)} の辞書を返す。
    ファイルが存在しない・読み込み失敗時は空辞書を返す（突合スキップ）。
    """
    p = Path(path)
    if not p.exists():
        logger.warning("所要時間マスタが存在しません: %s（突合をスキップします）", path)
        return {}

    try:
        df = pd.read_excel(p, sheet_name=0, engine="openpyxl")
    except Exception as e:
        logger.warning("所要時間マスタの読み込みに失敗しました: %s - %s（突合をスキップします）", path, e)
        return {}

    df.columns = [str(c).strip() for c in df.columns]
    station_col = None
    for c in ["駅名", "最寄り駅"]:
        if c in df.columns:
            station_col = c
            break
    if station_col is None:
        logger.warning("所要時間マスタに「駅名」または「最寄り駅」列がありません: %s", path)
        return {}

    time_col = None
    if "職場まで所要時間(分)" in df.columns:
        time_col = "職場まで所要時間(分)"
    else:
        for c in df.columns:
            if c != station_col and "所要時間" in str(c) and "分" in str(c):
                time_col = c
                break
    if time_col is None and len(df.columns) >= 2:
        time_col = df.columns[1]
    if time_col is None:
        logger.warning("所要時間マスタに所要時間列が見つかりません: %s", path)
        return {}

    result: Dict[str, int] = {}
    for _, row in df.iterrows():
        st = row.get(station_col)
        if pd.isna(st):
            continue
        st = str(st).strip()
        if not st:
            continue
        try:
            val = int(row[time_col])
        except (ValueError, TypeError):
            continue
        result[st] = val
    return result
