# -*- coding: utf-8 -*-
"""
所要時間マスタで「高野」「高田」が異常値（300分超・170分等）になる原因を調べるスクリプト。
Yahoo!乗換案内の取得URL・HTML内の駅名・各ルートのパース元テキストと抽出分数を表示する。
"""
import re
import time
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

YAHOO_TRANSIT_SEARCH = "https://transit.yahoo.co.jp/search/result"
ARRIVE_HOUR, ARRIVE_MINUTE = 8, 30
YAHOO_DATE_Y, YAHOO_DATE_M, YAHOO_DATE_D = 2026, 2, 10
YAHOO_SORT_ORDERS = (0, 1, 2)


def fetch_and_debug(from_station: str, to_station: str = "新橋"):
    """指定駅→到着地の検索を実行し、各ソート結果のHTMLから抽出した分数と元テキストを表示する。"""
    from_station = from_station.strip()
    to_station = to_station.strip()
    m1, m2 = ARRIVE_MINUTE // 10, ARRIVE_MINUTE % 10
    base_params = {
        "from": from_station,
        "to": to_station,
        "y": str(YAHOO_DATE_Y),
        "m": str(YAHOO_DATE_M).zfill(2),
        "d": str(YAHOO_DATE_D).zfill(2),
        "hh": str(ARRIVE_HOUR).zfill(2),
        "m1": str(m1),
        "m2": str(m2),
        "type": "2",
        "ticket": "ic",
        "expkind": "1",
        "userpass": "1",
        "ws": "3",
        "al": "1",
        "shin": "1",
        "ex": "1",
        "hb": "1",
        "lb": "1",
        "sr": "1",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    sort_names = {0: "到着時刻順", 1: "料金の安い順", 2: "乗換回数順"}
    all_minutes = []

    print(f"\n{'='*60}")
    print(f"検索: 【{from_station}】 → 【{to_station}】 (到着 {ARRIVE_HOUR}:{ARRIVE_MINUTE:02d})")
    print("=" * 60)

    for i, s in enumerate(YAHOO_SORT_ORDERS):
        if i > 0:
            time.sleep(0.3)
        params = {**base_params, "s": str(s)}
        url = f"{YAHOO_TRANSIT_SEARCH}?{urlencode(params, encoding='utf-8')}"
        print(f"\n--- ソート s={s} ({sort_names[s]}) ---")
        print(f"URL(先頭100文字): {url[:100]}...")

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            print(f"  取得失敗: {e}")
            continue

        # ページタイトルや検索条件を確認（どの駅として解釈されたか）
        soup = BeautifulSoup(html, "html.parser")
        title = soup.select_one("title")
        if title:
            print(f"  <title>: {title.get_text(strip=True)[:120]}")
        # 検索条件表示があれば（Yahooは「〇〇駅 → 〇〇駅」のように表示することがある）
        cond = soup.select_one(".searchCondition, .elmtSearchCondition, [class*='condition']")
        if cond:
            print(f"  条件表示: {cond.get_text(separator=' ', strip=True)[:150]}")

        # div.routeSummary ごとに li.time の全文とパース結果を表示
        for idx, div in enumerate(soup.select("div.routeSummary")):
            li_time = div.select_one("ul.summary li.time")
            if not li_time:
                continue
            raw_text = li_time.get_text(separator=" ", strip=True)
            before_paren = raw_text.split("（")[0].strip() if "（" in raw_text else raw_text
            m = re.search(r"(?:(\d+)時間)?\s*(\d+)分", before_paren)
            if m:
                hours = int(m.group(1)) if m.group(1) else 0
                mins = int(m.group(2))
                total = hours * 60 + mins
                all_minutes.append(total)
                in_range = 10 <= total <= 600
                print(f"  ルート{idx+1}: 抽出={total}分  (範囲内={in_range})")
                print(f"          括弧前テキスト: {repr(before_paren[:80])}")
                print(f"          元li.time全文:   {repr(raw_text[:100])}")
            else:
                print(f"  ルート{idx+1}: マッチせず テキスト: {repr(raw_text[:80])}")

        # 一覧リスト ul#rsltlst の li.time（要約）も確認
        for idx, li in enumerate(soup.select("ul#rsltlst li.time")):
            t = li.get_text(separator=" ", strip=True)
            print(f"  [一覧ルート{idx+1}] li.time: {repr(t[:80])}")

    print(f"\n→ 全ソートで抽出した分数のリスト: {sorted(all_minutes)}")
    print(f"→ 採用する最短時間(分): {min(all_minutes) if all_minutes else None}")
    return all_minutes


if __name__ == "__main__":
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("高野 → 新橋 の検索結果を調査します。")
    fetch_and_debug("高野", "新橋")

    print("\n\n")
    print("高田 → 新橋 の検索結果を調査します。")
    fetch_and_debug("高田", "新橋")
