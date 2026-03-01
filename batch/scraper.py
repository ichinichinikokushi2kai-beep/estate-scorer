"""
SUUMO 戸建・中古マンション検索結果のスクレイピング。
app_realestate.py から分離。Streamlit に依存しない。
"""
import re
import time
import logging
from typing import List, Dict, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup
import pandas as pd

logger = logging.getLogger(__name__)

MAX_PAGES_DEFAULT = 100


def build_page_url(url: str, page: int) -> str:
    """検索結果URLにページ番号を付与または書き換える。"""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["page"] = [str(page)]
    new_query = urlencode(qs, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def fetch_html(url: str, timeout: int = 10) -> Optional[str]:
    """指定URLからHTMLを取得する。"""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning("ページ取得エラー %s: %s", url[:80], e)
        return None


def parse_walk_and_station(access_text: str) -> tuple[Optional[str], Optional[int]]:
    """
    アクセス情報文字列から駅名と徒歩分数を抽出する。
    例: 'ＪＲ中央線「武蔵小金井」徒歩20分～21分' -> ('武蔵小金井', 20)
    """
    if not access_text:
        return None, None
    text = access_text.replace("\u3000", " ").strip()
    m = re.search(r"「(?P<station>.+?)」\s*徒歩\s*(?P<minutes>\d+)", text)
    if m:
        return m.group("station").strip(), int(m.group("minutes"))
    m2 = re.search(r"「(?P<station>.+?)」\s*歩(?P<minutes>\d+)分", text)
    if m2:
        return m2.group("station").strip(), int(m2.group("minutes"))
    m3 = re.search(r"(?P<station>.+?)\s*徒歩\s*(?P<minutes>\d+)", text)
    if m3:
        return m3.group("station").strip(" 「」"), int(m3.group("minutes"))
    return None, None


def parse_price_man(value: str) -> tuple[Optional[float], Optional[float]]:
    """
    「3180万円～3380万円」などをパースし、(価格①万円, 価格②万円) を返す。
    幅なしの場合は (x, x)。数値が取れない場合は (None, None)。
    """
    if not value or not isinstance(value, str):
        return None, None
    value = value.strip()
    nums = re.findall(r"(\d+(?:\.\d+)?)\s*万", value)
    if not nums:
        return None, None
    try:
        vals = [float(n) for n in nums]
        return min(vals), max(vals)
    except (ValueError, TypeError):
        return None, None


def parse_area(value: str) -> Optional[float]:
    """「191.59平米」「150.00m²」などから数値のみ抽出。"""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    m = re.search(r"(\d+(?:\.\d+)?)", value)
    if not m:
        return None
    try:
        return float(m.group(1))
    except (ValueError, TypeError):
        return None


def _parse_property_unit(unit) -> Optional[dict]:
    """1つの div.property_unit（新HTML構造）から物件情報を抽出。"""
    link_el = unit.select_one(".property_unit-title a[href*='nc_']")
    if not link_el or not link_el.get("href"):
        return None
    href = link_el["href"].strip()
    property_url = href if href.startswith("http") else f"https://suumo.jp{href}"
    m = re.search(r"nc_(\d+)", href)
    property_id = "nc_" + m.group(1) if m else None
    name = link_el.get_text(strip=True) if link_el else None

    price_raw: Optional[str] = None
    address: Optional[str] = None
    nearest_station: Optional[str] = None
    walk_minutes: Optional[int] = None
    land_area = None
    building_area = None
    layout: Optional[str] = None
    built_year: Optional[str] = None

    body = unit.select_one(".property_unit-body")
    if body:
        for dl in body.select("dl"):
            dts = dl.select("dt")
            dds = dl.select("dd")
            for dt_el, dd_el in zip(dts, dds):
                label = (dt_el.get_text(strip=True) or "").strip()
                value = (dd_el.get_text(strip=True) or "").strip()
                if label == "販売価格" and price_raw is None:
                    price_raw = value
                elif label == "所在地" and address is None:
                    address = value
                elif label == "沿線・駅" and nearest_station is None:
                    st_name, walk = parse_walk_and_station(value)
                    if st_name:
                        nearest_station = st_name
                    if walk is not None:
                        walk_minutes = walk
                elif label in ("敷地面積", "土地面積") and land_area is None:
                    land_area = parse_area(value)
                elif label in ("延床面積", "建物面積") and building_area is None:
                    building_area = parse_area(value)
                elif label == "間取り" and layout is None:
                    layout = value or None
                elif label in ("築年月", "築年数") and built_year is None:
                    built_year = value or None

    if not (price_raw or address or nearest_station or walk_minutes):
        return None
    price_min, price_max = parse_price_man(price_raw) if price_raw else (None, None)
    return {
        "物件名": name,
        "物件ID": property_id,
        "物件URL": property_url,
        "価格①": price_min,
        "価格②": price_max,
        "住所": address,
        "最寄り駅": nearest_station,
        "徒歩分数": walk_minutes,
        "土地面積": land_area,
        "建物面積": building_area,
        "間取り": layout,
        "築年数": built_year,
    }


def _parse_cassette_legacy(cassette) -> Optional[dict]:
    """旧HTML構造（li.cassette.js-bukkenCassette）から物件情報を抽出。"""
    name_el = cassette.select_one(".listtitleunit-title")
    name = name_el.get_text(strip=True) if name_el else None
    link_el = cassette.select_one(".listtitleunit-title a[href]")
    if not link_el or not link_el.get("href"):
        return None
    href = link_el["href"].strip()
    property_url = href if href.startswith("http") else f"https://suumo.jp{href}"
    m = re.search(r"nc_(\d+)", href)
    property_id = "nc_" + m.group(1) if m else None

    price_raw = address = nearest_station = None
    walk_minutes = None
    land_area = building_area = layout = built_year = None

    for dl in cassette.select("dl.tableinnerbox"):
        dt_el = dl.select_one(".tableinnerbox-title")
        dd_el = dl.select_one(".tableinnerbox-lead")
        if not dt_el or not dd_el:
            continue
        label = dt_el.get_text(strip=True)
        value = dd_el.get_text(strip=True)
        if label == "販売価格":
            price_raw = value
        elif label == "所在地":
            address = value
        elif label == "沿線・駅":
            st_name, walk = parse_walk_and_station(value)
            if st_name:
                nearest_station = st_name
            if walk is not None:
                walk_minutes = walk
        elif label in ("敷地面積", "土地面積"):
            land_area = parse_area(value)
        elif label in ("延床面積", "建物面積"):
            building_area = parse_area(value)
        elif label == "間取り":
            layout = value or None
        elif label in ("築年月", "築年数"):
            built_year = value or None

    if not (price_raw or address or nearest_station or walk_minutes):
        return None
    price_min, price_max = parse_price_man(price_raw) if price_raw else (None, None)
    return {
        "物件名": name,
        "物件ID": property_id,
        "物件URL": property_url,
        "価格①": price_min,
        "価格②": price_max,
        "住所": address,
        "最寄り駅": nearest_station,
        "徒歩分数": walk_minutes,
        "土地面積": land_area,
        "建物面積": building_area,
        "間取り": layout,
        "築年数": built_year,
    }


def scrape_suumo(url: str, warn_if_empty: bool = True) -> pd.DataFrame:
    """
    SUUMO検索結果一覧（新築・中古戸建）から1ページ分を取得し DataFrame を返す。
    新HTML構造（div.property_unit）に対応。旧構造（li.cassette.js-bukkenCassette）もフォールバックで対応。
    列: 物件名, 物件ID, 物件URL, 価格①, 価格②, 住所, 最寄り駅, 徒歩分数, 土地面積, 建物面積, 間取り, 築年数
    """
    html = fetch_html(url)
    if html is None:
        return pd.DataFrame()

    soup = BeautifulSoup(html, "html.parser")
    records: List[dict] = []

    # 新構造（2025年頃〜）: div.property_unit
    for unit in soup.select("div.property_unit"):
        row = _parse_property_unit(unit)
        if row:
            records.append(row)

    # 旧構造のフォールバック
    if not records:
        for cassette in soup.select("li.cassette.js-bukkenCassette"):
            row = _parse_cassette_legacy(cassette)
            if row:
                records.append(row)

    df = pd.DataFrame(records)
    if df.empty and warn_if_empty:
        logger.warning("物件情報が取得できませんでした: %s", url[:80])
    return df


def scrape_suumo_all_pages(
    url: str,
    max_pages: int = MAX_PAGES_DEFAULT,
    delay_seconds: float = 1.0,
) -> pd.DataFrame:
    """検索結果の全ページを順に取得し、1つのDataFrameにまとめて返す。"""
    all_records: List[dict] = []
    page = 1
    while page <= max_pages:
        page_url = build_page_url(url.strip(), page)
        df_page = scrape_suumo(page_url, warn_if_empty=(page == 1))
        if df_page.empty:
            break
        all_records.extend(df_page.to_dict("records"))
        if len(df_page) < 30:
            break
        page += 1
        if page <= max_pages:
            time.sleep(delay_seconds)
    return pd.DataFrame(all_records)


def scrape_url_list(
    url_list: List[Dict[str, str]],
    delay_seconds: float = 1.0,
) -> List[Dict]:
    """
    URLリストの各行についてスクレイピングし、種別・都道府県を付与したレコードのリストを返す。
    url_list: [{"種別": "新築戸建", "都道府県": "東京都", "URL": "https://..."}, ...]
    返却: 設計書スキーマに近い形式（property_id, property_url, property_name, price_min, price_max, ...）
    """
    all_records: List[Dict] = []
    for row in url_list:
        url = (row.get("URL") or row.get("url") or "").strip()
        if not url or "suumo.jp" not in url:
            continue
        category = (row.get("種別") or "").strip()
        prefecture = (row.get("都道府県") or "").strip()
        df_one = scrape_suumo_all_pages(url, delay_seconds=delay_seconds)
        if df_one.empty:
            continue
        for _, r in df_one.iterrows():
            rec = _row_to_property_record(r, category, prefecture)
            if rec:
                all_records.append(rec)
        time.sleep(delay_seconds)
    return all_records


def _row_to_property_record(
    r: pd.Series,
    category: str,
    prefecture: str,
) -> Optional[Dict]:
    """DataFrame 1行 + 種別・都道府県 を設計書の物件レコード形式に変換。"""
    pid = r.get("物件ID")
    if not pid:
        return None
    # 新築戸建の場合は築年数を「新築」に統一
    built = r.get("築年数")
    if category == "新築戸建":
        built = "新築"
    return {
        "property_id": pid,
        "property_url": r.get("物件URL"),
        "property_name": r.get("物件名"),
        "price_min": _num(r.get("価格①")),
        "price_max": _num(r.get("価格②")),
        "address": r.get("住所"),
        "nearest_station": r.get("最寄り駅"),
        "walk_minutes": _int(r.get("徒歩分数")),
        "land_area": _num(r.get("土地面積")),
        "building_area": _num(r.get("建物面積")),
        "layout": r.get("間取り"),
        "built_year": built,
        "category": category,
        "prefecture": prefecture,
    }


def _num(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v) -> Optional[int]:
    n = _num(v)
    return int(n) if n is not None else None
