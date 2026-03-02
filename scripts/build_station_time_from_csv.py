"""
docs/station 直下の4 CSV を読み、駅名ごとに4ファイル中最小の所要時間を採用して
station_time.xlsx を生成する。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from scripts.first_station_scores import get_first_station_score

STATION_DIR = Path(__file__).resolve().parent.parent / "docs" / "station"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "station_time.xlsx"

CSV_FILES = [
    "station_time_to_shimbashi_master (1).csv",
    "station_time_to_toranomon_master (1).csv",
    "station_time_to_toranomon_hills_master (1).csv",
    "station_time_to_uchisaiwaicho_master (1).csv",
]


def load_csv(path: Path) -> pd.DataFrame:
    """CSVを読み、駅名と所要時間の列を返す。"""
    for enc in ["utf-8-sig", "utf-8", "cp932"]:
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"CSVを読み込めません: {path}")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def main() -> None:
    station_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else STATION_DIR
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else OUTPUT_PATH

    # 4 CSV を読み、駅名をキーにマージ
    merged: pd.DataFrame | None = None
    time_cols: list[str] = []

    for fname in CSV_FILES:
        path = station_dir / fname
        if not path.exists():
            print(f"スキップ（存在しません）: {path}")
            continue
        df = load_csv(path)
        if "駅名" not in df.columns or len(df.columns) < 2:
            print(f"スキップ（列不足）: {path}")
            continue
        time_col = df.columns[1]
        df = df[["駅名", time_col]].copy()
        df["駅名"] = df["駅名"].astype(str).str.strip()
        df = df.dropna(subset=["駅名"])
        df = df[df["駅名"] != ""]

        if merged is None:
            merged = df.copy()
            time_cols = [time_col]
        else:
            merged = merged.merge(df, on="駅名", how="outer")
            time_cols.append(time_col)

    if merged is None or not time_cols:
        print("有効なCSVがありません")
        sys.exit(1)

    # 4ファイル中最小の所要時間を採用
    merged["職場まで所要時間(分)"] = merged[time_cols].min(axis=1)
    merged = merged[["駅名", "職場まで所要時間(分)"]].copy()

    # 数値でない行を除外
    merged["職場まで所要時間(分)"] = pd.to_numeric(merged["職場まで所要時間(分)"], errors="coerce")
    merged = merged.dropna(subset=["職場まで所要時間(分)"])
    merged["職場まで所要時間(分)"] = merged["職場まで所要時間(分)"].astype(int)

    # 始発駅スコア・近隣スコアを付与
    merged["始発駅スコア"] = merged["駅名"].apply(get_first_station_score)
    merged["近隣スコア"] = 0.0

    merged.to_excel(output_path, index=False, sheet_name="Sheet1")
    print(f"出力: {output_path}")
    print(f"  駅数: {len(merged)}")
    print(f"  始発駅スコア>0: {(merged['始発駅スコア'] > 0).sum()} 駅")


if __name__ == "__main__":
    main()
