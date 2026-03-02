"""
inferred_floors_by_ratio の閾値検証用サンプル調査スクリプト。

一覧から建物面積・土地面積を取得し、詳細ページで実階数（2階建て/3階建て）を取得。
ratio = 建物面積 / 土地面積 と実階数の対応を CSV に出力し、閾値（1.2, 1.5）の妥当性を検証する。
"""
import csv
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batch.scraper import fetch_html, scrape_suumo, build_page_url

# 詳細ページから階数を抽出する正規表現
FLOOR_PATTERNS = [
    re.compile(r"[23]階建(?:て)?", re.UNICODE),
    re.compile(r"[２３]階建(?:て)?", re.UNICODE),
    re.compile(r"木造[23]階建", re.UNICODE),
    re.compile(r"木造[２３]階建", re.UNICODE),
]


def extract_floors_from_detail_html(html: str) -> str | None:
    """
    詳細ページのHTMLから階数（2階建て/3階建て）を抽出。
    特徴ピックアップや設備・構造のテーブルに含まれる。
    """
    if not html:
        return None
    for pat in FLOOR_PATTERNS:
        m = pat.search(html)
        if m:
            text = m.group(0)
            # 全角→半角で正規化して返す
            if "3" in text or "３" in text:
                return "3階建て"
            if "2" in text or "２" in text:
                return "2階建て"
    return None


def infer_score_by_ratio(ratio: float) -> float:
    """extraction_conditions.yaml の inferred_floors_by_ratio に準拠。疑わしきは罰せず。"""
    return 0.5 if ratio <= 1.2 else 0.0


def run_survey(
    list_url: str,
    max_list_pages: int = 2,
    max_detail_per_page: int = 25,
    delay_seconds: float = 1.5,
    output_csv: str | Path = "docs/floors_survey_result.csv",
) -> list[dict]:
    """
    一覧をスクレイプし、建物面積・土地面積がある物件の詳細を取得して階数を突合。
    """
    results: list[dict] = []
    seen_ids: set[str] = set()

    for page in range(1, max_list_pages + 1):
        page_url = build_page_url(list_url.strip(), page)
        df = scrape_suumo(page_url, warn_if_empty=(page == 1))
        if df.empty:
            break

        # 建物面積・土地面積が両方ある物件のみ
        candidates = df[
            df["建物面積"].notna()
            & (df["建物面積"] > 0)
            & df["土地面積"].notna()
            & (df["土地面積"] > 0)
        ]

        count = 0
        for _, row in candidates.iterrows():
            if count >= max_detail_per_page:
                break
            pid = row.get("物件ID")
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)
            url = row.get("物件URL")
            if not url:
                continue

            building = float(row["建物面積"])
            land = float(row["土地面積"])
            ratio = building / land if land > 0 else None
            if ratio is None:
                continue

            html = fetch_html(url, timeout=15)
            actual_floors = extract_floors_from_detail_html(html) if html else None
            inferred_score = infer_score_by_ratio(ratio)

            results.append({
                "property_id": pid,
                "url": url,
                "building_area": building,
                "land_area": land,
                "ratio": round(ratio, 3),
                "actual_floors": actual_floors or "",
                "inferred_score": inferred_score,
            })
            count += 1
            time.sleep(delay_seconds)

        if len(df) < 30:
            break
        time.sleep(delay_seconds)

    # CSV 出力
    out_path = Path(output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["property_id", "url", "building_area", "land_area", "ratio", "actual_floors", "inferred_score"],
        )
        w.writeheader()
        w.writerows(results)

    return results


def print_summary(results: list[dict]) -> None:
    """調査結果のサマリを表示。"""
    if not results:
        print("対象物件が0件でした。")
        return

    print(f"\n=== サンプル調査結果（{len(results)} 件）===\n")

    # 実階数別の ratio 分布
    by_floors: dict[str, list[float]] = {"2階建て": [], "3階建て": [], "不明": []}
    for r in results:
        floors = (r.get("actual_floors") or "").strip()
        ratio = r.get("ratio")
        if ratio is None:
            continue
        if floors == "2階建て":
            by_floors["2階建て"].append(ratio)
        elif floors == "3階建て":
            by_floors["3階建て"].append(ratio)
        else:
            by_floors["不明"].append(ratio)

    for label, ratios in by_floors.items():
        if not ratios:
            continue
        print(f"【{label}】 {len(ratios)} 件")
        print(f"  ratio: min={min(ratios):.3f}, max={max(ratios):.3f}, avg={sum(ratios)/len(ratios):.3f}")
        # 閾値との対応
        le12 = sum(1 for x in ratios if x <= 1.2)
        le15 = sum(1 for x in ratios if 1.2 < x <= 1.5)
        gt15 = sum(1 for x in ratios if x > 1.5)
        print(f"  ratio<=1.2: {le12}件, 1.2<ratio<=1.5: {le15}件, ratio>1.5: {gt15}件")
        print()

    # 推定スコアと実階数の一致率（疑わしきは罰せず: ratio<=1.2→+0.5, それ以上→0点）
    correct = 0
    total = 0
    for r in results:
        floors = (r.get("actual_floors") or "").strip()
        score = r.get("inferred_score")
        if floors and score is not None:
            total += 1
            # 誤りは 3階建てに+0.5 をつけた場合のみ
            if not (floors == "3階建て" and score == 0.5):
                correct += 1

    if total > 0:
        print(f"推定スコアと実階数の一致: {correct}/{total} ({100*correct/total:.1f}%)")
        print("  （ratio<=1.2→+0.5, それ以上→0点。3階建てに+0.5は誤り）")


def main():
    import argparse
    import pandas as pd

    parser = argparse.ArgumentParser(description="inferred_floors_by_ratio 閾値検証用サンプル調査")
    parser.add_argument("--limit", type=int, default=15, help="詳細取得する最大件数（デフォルト: 15）")
    args = parser.parse_args()

    base = Path(__file__).resolve().parent.parent
    url_path = base / "docs" / "suumo_url_list.csv"
    if not url_path.exists():
        print(f"URLリストが見つかりません: {url_path}")
        sys.exit(1)

    df = pd.read_csv(url_path, encoding="utf-8")
    row = df.iloc[0]
    list_url = row.get("URL", row.get("url", ""))
    if not list_url or "suumo" not in list_url:
        print("有効なSUUMO URLがありません")
        sys.exit(1)

    output = base / "docs" / "floors_survey_result.csv"
    print(f"一覧URL: {list_url[:70]}...")
    print(f"出力先: {output}")
    print(f"詳細ページ取得中（最大{args.limit}件、遅延1.2秒）...")

    results = run_survey(
        list_url=list_url,
        max_list_pages=2,
        max_detail_per_page=args.limit,
        delay_seconds=1.2,
        output_csv=output,
    )

    print_summary(results)
    print(f"\nCSV保存: {output}")


if __name__ == "__main__":
    main()
