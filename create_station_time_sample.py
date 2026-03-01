# -*- coding: utf-8 -*-
"""station_time.xlsx のサンプルを作成する。既存ファイルがある場合は上書きしない。"""
import pandas as pd
from pathlib import Path

path = Path(__file__).parent / "station_time.xlsx"
if path.exists():
    print(f"{path} already exists. Skipping.")
else:
    df = pd.DataFrame({
        "駅名": ["新宿", "渋谷", "品川", "東京", "武蔵小金井"],
        "職場まで所要時間(分)": [15, 13, 8, 3, 28],
    })
    df.to_excel(path, index=False, sheet_name="Sheet1")
    print(f"Created {path}")
