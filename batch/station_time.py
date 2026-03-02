"""
所要時間マスタ（station_time.xlsx）の読み込み。
列: 駅名 or 最寄り駅, 職場まで所要時間(分), 始発駅スコア, 近隣スコア（任意）
"""
import logging
from pathlib import Path
from typing import Any, Dict

import pandas as pd

logger = logging.getLogger(__name__)


def load_station_time_master(path: str) -> Dict[str, Dict[str, Any]]:
    """
    station_time.xlsx を読み、{駅名: {time, first_train_score, neighborhood_score}} の辞書を返す。
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

    first_col = "始発駅スコア" if "始発駅スコア" in df.columns else ("始発駅フラグ" if "始発駅フラグ" in df.columns else None)
    neighbor_col = "近隣スコア" if "近隣スコア" in df.columns else ("近隣フラグ" if "近隣フラグ" in df.columns else None)

    result: Dict[str, Dict[str, Any]] = {}
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
        if first_col:
            fv = row.get(first_col)
            first_score = _to_float(fv) if first_col == "始発駅スコア" else (0.5 if _to_int(fv) == 1 else 0.0)
        else:
            first_score = 0.0
        neighbor_score = _to_float(row.get(neighbor_col)) if neighbor_col else 0.0
        result[st] = {"time": val, "first_train_score": first_score, "neighborhood_score": neighbor_score}
    return result


def _to_int(v) -> int:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def _to_float(v) -> float:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0.0
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0
