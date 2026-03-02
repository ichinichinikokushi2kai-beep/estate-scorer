# -*- coding: utf-8 -*-
"""station_time.xlsx のサンプルを作成する。既存ファイルがある場合は上書きしない。"""
import argparse
import sys
from pathlib import Path

import pandas as pd

path = Path(__file__).resolve().parent / "station_time.xlsx"
parser = argparse.ArgumentParser()
parser.add_argument("--force", action="store_true", help="既存ファイルを上書きする")
args = parser.parse_args()
if path.exists() and not args.force:
    print(f"{path} already exists. Skipping. (--force で上書き)")
else:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from scripts.first_station_scores import get_first_station_score

    stations = ["新宿", "渋谷", "品川", "東京", "武蔵小金井"]
    times = [15, 13, 8, 3, 28]
    first_scores = [get_first_station_score(s) for s in stations]
    df = pd.DataFrame({
        "駅名": stations,
        "職場まで所要時間(分)": times,
        "始発駅スコア": first_scores,
        "近隣スコア": [0.0] * len(stations),
    })
    df.to_excel(path, index=False, sheet_name="Sheet1")
    print(f"Created {path}")
