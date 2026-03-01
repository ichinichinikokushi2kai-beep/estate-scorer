"""SUUMO 検索結果ページのHTML構造を確認する（デバッグ用）。"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batch.scraper import fetch_html
from bs4 import BeautifulSoup

URL = "https://suumo.jp/jj/bukken/ichiran/JJ010FJ001/?ar=030&ta=13&bs=020&kt=6000&kb=4000&page=1"

def main():
    html = fetch_html(URL, timeout=15)
    if not html:
        print("HTML取得失敗")
        return
    print(f"HTML長: {len(html)} 文字")

    soup = BeautifulSoup(html, "html.parser")

    # 現在のセレクタ
    cassettes = soup.select("li.cassette.js-bukkenCassette")
    print(f"li.cassette.js-bukkenCassette: {len(cassettes)} 件")

    # 別の候補セレクタ
    for sel in ["li.cassette", ".cassette", "[class*='cassette']", "article", ".property"]:
        els = soup.select(sel)
        if els:
            print(f"  {sel}: {len(els)} 件")
            # 最初の1要素のタグとクラスを表示
            e = els[0]
            print(f"    最初の要素: <{e.name}> class={e.get('class')}")
            # 子に .listtitleunit-title や .tableinnerbox があるか
            t1 = e.select_one(".listtitleunit-title")
            t2 = e.select("dl.tableinnerbox")
            print(f"    .listtitleunit-title: {t1 is not None}, dl.tableinnerbox: {len(t2)} 個")

    # 物件名らしきテキストを含む要素
    if "物件名" in html and "販売価格" in html:
        print("  HTML内に「物件名」「販売価格」の文字列は含まれています")
    else:
        print("  HTML内に「物件名」または「販売価格」が含まれていません")

    # 旧セレクタがHTML内に存在するか
    for token in ["listtitleunit-title", "tableinnerbox", "tableinnerbox-title", "tableinnerbox-lead"]:
        print(f"  HTML内に '{token}': {'あり' if token in html else 'なし'}")

    # 物件カードらしき要素を探す（nc_ リンクを含む親）
    nc_ids = re.findall(r"nc_?\d+", html[:50000])
    print(f"  HTML前半の nc_ 物件ID: {len(nc_ids)} 個")

    # nc_ を含むリンクの親をたどって物件カードのブロックを特定
    first_nc_link = soup.find("a", href=re.compile(r"nc_\d+"))
    if first_nc_link:
        href = first_nc_link.get("href", "")
        print(f"  最初の nc_ リンク: {href[:70]}...")
        # 親のうち、複数の物件で共通しそうなブロックを探す（例: li, div.cassette, section）
        p = first_nc_link.parent
        level = 0
        while p and level < 15:
            cls = p.get("class") or []
            cls_str = " ".join(cls) if isinstance(cls, list) else str(cls)
            tag_cls = f"<{p.name} class='{cls_str[:50]}'>"
            # 同じレベルで兄弟の nc_ リンク数
            siblings_nc = len(p.find_all("a", href=re.compile(r"nc_\d+"), limit=5))
            print(f"    親 L{level}: {tag_cls} (子孫のnc_リンク: {siblings_nc})")
            p = p.parent
            level += 1
    else:
        print("  nc_ リンクが見つかりません")

    # div.property_unit 1つの子要素とラベル・値の候補
    units = soup.select("div.property_unit")
    print(f"\n  div.property_unit: {len(units)} 件")
    if units:
        u = units[0]
        body = u.select_one(".property_unit-body")
        if body:
            # 直下の dl や div でラベル・値のペアを探す
            for dl in body.select("dl"):
                dts = dl.select("dt")
                dds = dl.select("dd")
                for i, (dt, dd) in enumerate(zip(dts, dds)):
                    if i >= 5:
                        break
                    lbl = (dt.get_text(strip=True) or "")[:20]
                    val = (dd.get_text(strip=True) or "")[:35]
                    print(f"    dt/dd: [{lbl}] -> {val}")
            # dt/dd がなければ div の行
            if not body.select("dl"):
                for row in body.select("[class*='line']"):
                    print(f"    row class: {row.get('class')} text: {(row.get_text(strip=True) or '')[:50]}")

if __name__ == "__main__":
    main()
