"""
全物件一覧HTML（条件ポイント降順）の生成。
データソースは「今回の検索で取得した物件のうち閾値以上のもの」のみ。
"""
import html
from pathlib import Path
from typing import Any, Dict, List


def generate_properties_list_html(
    properties: List[Dict[str, Any]],
    output_path: str,
) -> None:
    """
    物件リストを条件ポイント（extraction_score）降順で並べ、HTML を生成して保存する。
    properties には extraction_score が含まれていること。
    """
    sorted_list = sorted(
        properties,
        key=lambda p: (p.get("extraction_score") is None, -(p.get("extraction_score") or 0)),
    )

    rows_html = []
    for p in sorted_list:
        rows_html.append(_row_html(p))

    html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SUUMO 全物件一覧（条件ポイント降順）</title>
  <style>
    body {{ font-family: sans-serif; margin: 1rem; background: #f5f5f5; }}
    h1 {{ font-size: 1.2rem; }}
    table {{ border-collapse: collapse; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    th, td {{ border: 1px solid #ddd; padding: 0.4rem 0.6rem; text-align: left; }}
    th {{ background: #333; color: #fff; }}
    tr:nth-child(even) {{ background: #f9f9f9; }}
    a {{ color: #06c; }}
    .score {{ font-weight: bold; }}
  </style>
</head>
<body>
  <h1>SUUMO 全物件一覧（条件ポイント降順）</h1>
  <p>直近の検索でヒットした物件のみ表示しています。（{len(sorted_list)} 件）</p>
  <table>
    <thead>
      <tr>
        <th>ポイント</th>
        <th>物件名</th>
        <th>価格</th>
        <th>住所</th>
        <th>最寄り駅</th>
        <th>徒歩</th>
        <th>種別</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>
</body>
</html>
"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)


def _row_html(p: Dict[str, Any]) -> str:
    score = p.get("extraction_score")
    score_str = str(score) if score is not None else "-"
    name = html.escape((p.get("property_name") or "").strip())
    url = p.get("property_url") or "#"
    url = html.escape(url)
    price = _format_price(p)
    addr = html.escape((p.get("address") or "")[:60])
    station = html.escape((p.get("nearest_station") or ""))
    walk = p.get("walk_minutes")
    walk_str = f"{walk}分" if walk is not None else "-"
    category = html.escape((p.get("category") or ""))

    return f"""      <tr>
        <td class="score">{score_str}</td>
        <td><a href="{url}" target="_blank" rel="noopener">{name or "(なし)"}</a></td>
        <td>{html.escape(price)}</td>
        <td>{addr}</td>
        <td>{station}</td>
        <td>{walk_str}</td>
        <td>{category}</td>
      </tr>
"""


def _format_price(p: Dict[str, Any]) -> str:
    pmin = p.get("price_min")
    pmax = p.get("price_max")
    if pmin is not None and pmax is not None:
        if pmin == pmax:
            return f"{pmin}万円"
        return f"{pmin}～{pmax}万円"
    if pmin is not None:
        return f"{pmin}万円～"
    if pmax is not None:
        return f"～{pmax}万円"
    return "-"
