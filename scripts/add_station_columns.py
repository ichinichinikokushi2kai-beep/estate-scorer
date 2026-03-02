"""
所要時間マスタ（station_time.xlsx）に 始発駅スコア と 近隣スコア 列を追加する。

- 始発駅スコア: 通勤コンパスのランクに応じて設定（多い→1.0, 中くらい→0.5, 少ない/乗り入れ先→0.25）
  出典: https://en-culture.net/commute/first.html
- 近隣スコア: 0 で追加。ユーザーが手動で近さに応じたポイントを入れる
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from scripts.first_station_scores import get_first_station_score

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "station_time.xlsx"


def add_columns(path: Path) -> None:
    if not path.exists():
        print(f"ファイルが存在しません: {path}")
        print("先に station_time.xlsx を作成してください（create_station_time_sample.py 等）")
        sys.exit(1)

    df = pd.read_excel(path, sheet_name=0, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    station_col = None
    for c in ["駅名", "最寄り駅"]:
        if c in df.columns:
            station_col = c
            break
    if station_col is None:
        print(f"駅名列が見つかりません。列: {list(df.columns)}")
        sys.exit(1)

    # 始発駅スコア: 既存列があれば上書き、なければ追加。旧「始発駅フラグ」があればリネーム
    if "始発駅スコア" not in df.columns:
        if "始発駅フラグ" in df.columns:
            # 旧フラグ(0/1)をスコアに変換: 1→0.5, 0→0
            df["始発駅スコア"] = df["始発駅フラグ"].apply(lambda x: 0.5 if x == 1 else 0.0)
            df = df.drop(columns=["始発駅フラグ"])
        else:
            df["始発駅スコア"] = 0.0
    for i, row in df.iterrows():
        st = row.get(station_col)
        if pd.isna(st):
            continue
        st = str(st).strip()
        if not st:
            continue
        score = get_first_station_score(st)
        if score > 0:
            df.at[i, "始発駅スコア"] = score

    # 近隣スコア: 既存列がなければ追加。旧「近隣フラグ」があればリネーム
    if "近隣スコア" not in df.columns:
        if "近隣フラグ" in df.columns:
            df["近隣スコア"] = df["近隣フラグ"].astype(float)
            df = df.drop(columns=["近隣フラグ"])
        else:
            df["近隣スコア"] = 0

    df.to_excel(path, index=False, sheet_name="Sheet1")
    first_positive = (df["始発駅スコア"] > 0).sum()
    print(f"更新完了: {path}")
    print(f"  始発駅スコア>0: {first_positive} 駅")
    print(f"  近隣スコア: 手動で近さに応じたポイントを入れてください")


if __name__ == "__main__":
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    add_columns(p)
