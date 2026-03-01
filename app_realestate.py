import re
import time
from typing import List, Dict, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, quote

import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st


# 新橋駅までの標準乗車時間（分）。駅名のみをキーにする。
#
# 【取得方法】
# 1. 乗換案内（ジョルダン、Yahoo!乗換案内、駅すぱあと等）で
#    「各駅 → 新橋」の最短乗車時間を調べ、分単位でここに追加する。
# 2. 国土交通省のオープンデータや、乗換案内API（有料の場合は利用規約要確認）を
#    使って一括取得する方法もある。
# 3. スクレイピング結果のCSVで「最寄り駅」に出てきた駅から優先して追加すると、
#    「合計50分以内」フラグが有効になる。
#
STATION_TIME_TO_SHIMBASHI: Dict[str, int] = {
    "新宿": 15,
    "渋谷": 13,
    "池袋": 20,
    "品川": 8,
    "東京": 3,
    "上野": 15,
    "横浜": 25,
    "大宮": 35,
    "千葉": 40,
    "川崎": 18,
    # 以下は戸建検索でよく出る駅の目安（乗換案内で要確認）
    "武蔵小金井": 28,
    "東小金井": 26,
    "国分寺": 30,
    "国立": 32,
    "立川": 45,
    "玉川上水": 42,
    "東久留米": 32,
    "ひばりヶ丘": 35,
    "保谷": 38,
    "大泉学園": 40,
    "花小金井": 38,
    "恋ヶ窪": 32,
    "東伏見": 36,
    "稲城": 48,
    "昭島": 55,
    "西武立川": 48,
    "分倍河原": 38,
    "京王多摩センター": 50,
    "小平": 40,
    "鷹の台": 38,
    "東大和市": 52,
    "武蔵大和": 50,
    "中村橋": 32,
    "石神井公園": 35,
    "桜台": 30,
    "光が丘": 35,
    "氷川台": 28,
    "練馬": 28,
    "狛江": 28,
}


def build_page_url(url: str, page: int) -> str:
    """検索結果URLにページ番号を付与または書き換える。"""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["page"] = [str(page)]
    new_query = urlencode(qs, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def fetch_html(url: str, timeout: int = 10) -> Optional[str]:
    """指定URLからHTMLを取得する（シンプルなラッパー）。"""
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
        st.error(f"ページ取得中にエラーが発生しました: {e}")
        return None


# Yahoo!乗換案内 検索URL
YAHOO_TRANSIT_SEARCH = "https://transit.yahoo.co.jp/search/result"

# 到着時刻 8:30 を指定するパラメータ（ユーザー提供の実URLに準拠）
# m1=十の位, m2=一の位 → m1=3, m2=0 で 30分。type=2 で到着時刻検索。
ARRIVE_HOUR, ARRIVE_MINUTE = 8, 30
# 検索に使う日付（平日を想定。y=年, m=月, d=日）
YAHOO_DATE_Y, YAHOO_DATE_M, YAHOO_DATE_D = 2026, 2, 10
# 複数ソートで取得して最短を取る。s=0:到着時刻順, s=1:料金の安い順, s=2:乗換回数順
YAHOO_SORT_ORDERS = (0, 1, 2)


def _parse_route_durations_from_html(html: str) -> List[int]:
    """
    Yahoo!乗換案内の結果HTMLから、各ルートの「出発→到着 所要時間」の所要時間のみを抽出する。
    div.routeSummary > ul.summary > li.time のテキスト（例: "07:32発→08:29着 57分（乗車 49分）"）
    のうち、括弧より前の「57分」だけを採用し、乗車時間（49分）は含めない。
    """
    soup = BeautifulSoup(html, "html.parser")
    results: List[int] = []
    for li in soup.select("div.routeSummary ul.summary li.time"):
        text = li.get_text(separator=" ", strip=True)
        # 括弧より前の部分だけを使う（「57分（乗車 49分）」→「57分」のみ）
        if "（" in text:
            text = text.split("（")[0].strip()
        m = re.search(r"(?:(\d+)時間)?\s*(\d+)分", text)
        if not m:
            continue
        hours = int(m.group(1)) if m.group(1) else 0
        mins = int(m.group(2))
        total = hours * 60 + mins
        if 10 <= total <= 600:
            results.append(total)
    return results


def _parse_all_durations_minutes(html: str) -> List[int]:
    """
    乗換案内の結果HTMLから各ルートの所要時間を抽出する。
    まず routeSummary の li.time から括弧前の所要時間のみを取得し、
    取れなければ従来の正規表現で「乗換」直後を除いた分数を集める。
    """
    # 優先: 出発→到着の所要時間（括弧前）を明示的に取得
    by_structure = _parse_route_durations_from_html(html)
    if by_structure:
        return by_structure
    # フォールバック: 全文から○分を拾い、「乗換」直後は除外
    pattern = re.compile(r"(?:(\d+)時間)?\s*(\d+)分")
    results: List[int] = []
    for m in pattern.finditer(html):
        start = max(0, m.start() - 20)
        if "乗換" in html[start : m.start()]:
            continue
        hours = int(m.group(1)) if m.group(1) else 0
        mins = int(m.group(2))
        total = hours * 60 + mins
        if 10 <= total <= 600:
            results.append(total)
    return results


def fetch_time_to_station(
    from_station: str,
    to_station: str,
    arrive_hour: int = ARRIVE_HOUR,
    arrive_minute: int = ARRIVE_MINUTE,
    timeout: int = 15,
) -> Optional[int]:
    """
    指定駅から指定駅までの所要時間（分）を Yahoo!乗換案内 で検索する。
    到着時刻 8:30 で検索し、表示された経路のうち最も短い所要時間を返す。
    """
    if not from_station or not from_station.strip():
        return None
    if not to_station or not to_station.strip():
        return None
    from_station = from_station.strip()
    to_station = to_station.strip()
    # m1=分の十の位, m2=分の一の位（例: 30分 → m1=3, m2=0）
    m1, m2 = arrive_minute // 10, arrive_minute % 10
    base_params = {
        "from": from_station,
        "to": to_station,
        "y": str(YAHOO_DATE_Y),
        "m": str(YAHOO_DATE_M).zfill(2),
        "d": str(YAHOO_DATE_D).zfill(2),
        "hh": str(arrive_hour).zfill(2),
        "m1": str(m1),
        "m2": str(m2),
        "type": "2",  # 到着時刻で検索
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
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
    }
    all_minutes: List[int] = []
    try:
        # 到着時刻順・料金順・乗換回数順の3種類を取得し、全ルートの最短を採用する
        for i, s in enumerate(YAHOO_SORT_ORDERS):
            if i > 0:
                time.sleep(0.3)  # 同一駅の連続リクエスト間で少し待つ
            params = {**base_params, "s": str(s)}
            url = f"{YAHOO_TRANSIT_SEARCH}?{urlencode(params, encoding='utf-8')}"
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            all_minutes.extend(_parse_all_durations_minutes(resp.text))
        return min(all_minutes) if all_minutes else None
    except Exception:
        return None


def get_times_to_shimbashi_for_stations(
    station_list: List[str],
    delay_seconds: float = 2.0,
) -> Dict[str, Optional[int]]:
    """
    候補駅リストについて、各駅→新橋の所要時間（分）を乗換案内で取得し辞書で返す。
    重複駅は1回だけ検索する。到着8:30・最短所要時間を採用。
    """
    seen = set()
    result: Dict[str, Optional[int]] = {}
    for station in station_list:
        s = (station or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        result[s] = fetch_time_to_station(s, "新橋")
        time.sleep(delay_seconds)
    return result


def parse_walk_and_station(access_text: str) -> tuple[Optional[str], Optional[int]]:
    """
    アクセス情報文字列から駅名と徒歩分数を抽出する。
    駅名は「」内の文字列のみを返す（路線名は含めない）。
    例: 'ＪＲ中央線「武蔵小金井」徒歩20分～21分' -> ('武蔵小金井', 20)
    """
    if not access_text:
        return None, None

    # 全角スペースなどをやや正規化
    text = access_text.replace("\u3000", " ").strip()

    # 「駅名」徒歩XX分 または 「駅名」徒歩XX分～YY分（SUUMOの表記）
    m = re.search(r"「(?P<station>.+?)」\s*徒歩\s*(?P<minutes>\d+)", text)
    if m:
        station = m.group("station").strip()
        minutes = int(m.group("minutes"))
        return station, minutes

    # 「駅名」歩XX分（旧表記・他サイト用）
    m2 = re.search(r"「(?P<station>.+?)」\s*歩(?P<minutes>\d+)分", text)
    if m2:
        station = m2.group("station").strip()
        minutes = int(m2.group("minutes"))
        return station, minutes

    # 駅名 徒歩XX分 形式のフォールバック（「」なし）
    m3 = re.search(r"(?P<station>.+?)\s*徒歩\s*(?P<minutes>\d+)", text)
    if m3:
        station = m3.group("station").strip(" 「」")
        minutes = int(m3.group("minutes"))
        return station, minutes

    return None, None


def _parse_price_man(value: str) -> tuple:
    """
    「3180万円～3380万円」「3500万円」などをパースし、(価格①万円, 価格②万円) を返す。
    幅なしの場合は (x, x)。数値が取れない場合は (None, None)。
    """
    if not value or not isinstance(value, str):
        return None, None
    value = value.strip()
    # 〇〇万～〇〇万 または 〇〇万円～〇〇万円
    nums = re.findall(r"(\d+(?:\.\d+)?)\s*万", value)
    if not nums:
        return None, None
    try:
        vals = [float(n) for n in nums]
        return min(vals), max(vals)
    except (ValueError, TypeError):
        return None, None


def _parse_area(value: str):
    """
    「191.59平米」「150.00m²」などから数値のみ抽出。取れない場合は None。
    """
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


def load_station_time_master(file) -> Dict[str, int]:
    """
    駅所要時間マスタCSV（駅名 → 職場まで所要時間(分)）を読み、辞書で返す。
    列: 駅名 or 最寄り駅, 職場まで所要時間(分) または 所要時間・分 を含む列。UTF-8 / Shift_JIS 対応。
    """
    if file is None:
        return {}
    try:
        file.seek(0)
        df = pd.read_csv(file, encoding="utf-8-sig")
    except Exception:
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding="cp932")
        except Exception:
            return {}
    df.columns = [str(c).strip() for c in df.columns]
    station_col = None
    for c in ["駅名", "最寄り駅"]:
        if c in df.columns:
            station_col = c
            break
    if station_col is None:
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
        return {}
    result: Dict[str, int] = {}
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
        result[st] = val
    return result


# 全ページ取得時の上限（1ページあたり約30件想定）
MAX_PAGES_DEFAULT = 100


def scrape_suumo(url: str, warn_if_empty: bool = True) -> pd.DataFrame:
    """
    SUUMOの検索結果一覧（新築・中古戸建）から
    物件名、価格①/価格②（万円）、住所、最寄り駅、徒歩分数、土地面積、建物面積、間取り、築年数 を抽出してDataFrameを返す。
    1ページ分のみ取得する。

    ※SUUMOのHTML構造が変更されると動かなくなる可能性があります。
    """
    html = fetch_html(url)
    if html is None:
        return pd.DataFrame()

    soup = BeautifulSoup(html, "html.parser")

    records = []

    for cassette in soup.select("li.cassette.js-bukkenCassette"):
        name = None
        name_el = cassette.select_one(".listtitleunit-title")
        if name_el:
            name = name_el.get_text(strip=True)

        property_id: Optional[str] = None
        property_url: Optional[str] = None
        link_el = cassette.select_one(".listtitleunit-title a[href]")
        if link_el and link_el.get("href"):
            href = link_el["href"].strip()
            if href:
                property_url = href if href.startswith("http") else f"https://suumo.jp{href}"
                m = re.search(r"nc_(\d+)", href)
                if m:
                    property_id = m.group(1)

        price_raw: Optional[str] = None
        address: Optional[str] = None
        nearest_station: Optional[str] = None
        walk_minutes: Optional[int] = None
        land_area = None
        building_area = None
        layout: Optional[str] = None
        built_year: Optional[str] = None

        for dl in cassette.select("dl.tableinnerbox"):
            dt_el = dl.select_one(".tableinnerbox-title")
            dd_el = dl.select_one(".tableinnerbox-lead")
            if not dt_el or not dd_el:
                continue
            label = dt_el.get_text(strip=True)
            value = dd_el.get_text(strip=True)

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
                land_area = _parse_area(value)
            elif label in ("延床面積", "建物面積") and building_area is None:
                building_area = _parse_area(value)
            elif label == "間取り" and layout is None:
                layout = value if value else None
            elif label in ("築年月", "築年数") and built_year is None:
                built_year = value if value else None

        if not (price_raw or address or nearest_station or walk_minutes):
            continue

        price_min, price_max = _parse_price_man(price_raw) if price_raw else (None, None)

        row = {
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
        records.append(row)

    df = pd.DataFrame(records)

    if df.empty and warn_if_empty:
        st.warning("物件情報が取得できませんでした。URLや検索条件、ページ構造をご確認ください。")

    return df


def scrape_suumo_all_pages(
    url: str,
    max_pages: int = MAX_PAGES_DEFAULT,
    delay_seconds: float = 1.0,
) -> pd.DataFrame:
    """
    検索結果の全ページを順に取得し、1つのDataFrameにまとめて返す。
    取得件数が0件のページに達するか、max_pages に達したら終了する。
    """
    all_records: List[dict] = []
    page = 1

    while page <= max_pages:
        page_url = build_page_url(url.strip(), page)
        df_page = scrape_suumo(page_url, warn_if_empty=(page == 1))

        if df_page.empty:
            break

        all_records.extend(df_page.to_dict("records"))

        # 1ページあたりの表示件数（30など）より少なければ最終ページとみなす
        if len(df_page) < 30:
            break

        page += 1
        if page <= max_pages:
            time.sleep(delay_seconds)

    return pd.DataFrame(all_records)


def main() -> None:
    st.set_page_config(
        page_title="SUUMO戸建スクレイピング（プロトタイプ）",
        page_icon="🏠",
        layout="wide",
    )

    st.title("SUUMO 新築・中古戸建スクレイピング（プロトタイプ）")
    tab_scrape, tab_master = st.tabs(["SUUMOスクレイピング", "所要時間マスタ作成"])

    with tab_scrape:
        st.markdown(
            """
            **URLリストCSV** をアップロードすると、リスト内の各URLを順に検索し、  
            結果を **種別** と **都道府県** 付きで1つのCSVにマージして出力します。

            - リストCSVの列: **種別** / **都道府県** / **URL**
            - 抽出項目: 物件名 / 価格①・価格②（万円） / 住所 / 最寄り駅 / 徒歩分数 / 土地面積 / 建物面積 / 間取り / 築年数
            - 出力CSVにはどの検索結果からか分かるよう **種別** と **都道府県** を先頭列で付与します。
            """
        )
        url_list_file = st.file_uploader(
            "URLリストCSVをアップロード",
            type=["csv"],
            key="url_list",
            help="列に 種別, 都道府県, URL を含むCSV。UTF-8 または Shift_JIS 対応。",
        )
        fetch_all_pages = st.checkbox(
            "各URLで全ページを取得する（件数が多いと時間がかかります）",
            value=True,
            help="オフにすると各URLの1ページ分（約30件）のみ取得します。",
        )
        col1, col2 = st.columns([1, 3])
        with col1:
            scrape_button = st.button("スクレイピングを実行", type="primary")

    if scrape_button:
        if url_list_file is None:
            st.error("URLリストのCSVをアップロードしてください。")
            return

        # CSV読み込み（UTF-8 / Shift_JIS を試す）
        url_list_file.seek(0)
        try:
            list_df = pd.read_csv(url_list_file, encoding="utf-8")
        except Exception:
            url_list_file.seek(0)
            list_df = pd.read_csv(url_list_file, encoding="cp932")

        # 列名の正規化、URL列を探す
        list_df.columns = [c.strip() for c in list_df.columns]
        url_col = None
        for c in ["URL", "url", "Url"]:
            if c in list_df.columns:
                url_col = c
                break
        if "種別" not in list_df.columns or "都道府県" not in list_df.columns or url_col is None:
            st.error("CSVに「種別」「都道府県」および「URL」列を含めてください。")
            return

        list_df = list_df[["種別", "都道府県", url_col]].dropna(subset=[url_col])
        list_df = list_df[list_df[url_col].astype(str).str.contains("suumo.jp", na=False)]

        if list_df.empty:
            st.error("有効なSUUMOのURLが1件もありません。")
            return

        all_records = []
        total = len(list_df)
        progress_bar = st.progress(0, text="0件目を取得中…")
        status = st.empty()

        for n, (_, row) in enumerate(list_df.iterrows(), start=1):
            status.info(f"({n}/{total}) 種別: {row['種別']} / 都道府県: {row['都道府県']} を取得中…")
            progress_bar.progress(n / total, text=f"{n}/{total} 件目を取得中…")

            url = str(row[url_col]).strip()
            if fetch_all_pages:
                df_one = scrape_suumo_all_pages(url, delay_seconds=1.0)
            else:
                df_one = scrape_suumo(url, warn_if_empty=(n == 1))

            if not df_one.empty:
                df_one.insert(0, "都道府県", row["都道府県"])
                df_one.insert(0, "種別", row["種別"])
                recs = df_one.to_dict("records")
                # 新築戸建の場合は築年数を「新築」に統一
                shubetsu = str(row.get("種別", "")).strip()
                for r in recs:
                    if shubetsu == "新築戸建":
                        r["築年数"] = "新築"
                all_records.extend(recs)

            time.sleep(0.5)

        progress_bar.progress(1.0, text="完了")
        status.empty()

        df = pd.DataFrame(all_records)

        if not df.empty:
            # 数値列を明示的に数値型に（価格は万円、面積はm²）
            for col in ("価格①", "価格②", "土地面積", "建物面積", "徒歩分数"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            # 列順: 種別, 都道府県, 物件名, 物件ID, 物件URL, 価格①, 価格②, 住所, 最寄り駅, 徒歩分数, 土地面積, 建物面積, 間取り, 築年数
            out_cols = [
                "種別", "都道府県", "物件名", "物件ID", "物件URL",
                "価格①", "価格②", "住所", "最寄り駅", "徒歩分数",
                "土地面積", "建物面積", "間取り", "築年数",
            ]
            ordered = [c for c in out_cols if c in df.columns]
            ordered += [c for c in df.columns if c not in out_cols]
            df = df[ordered]

            st.subheader("検索結果（マージ済み）")
            st.dataframe(df, use_container_width=True)

            csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="CSVをダウンロード",
                data=csv_bytes,
                file_name="suumo_kodate_results_merged.csv",
                mime="text/csv",
            )
            st.info(f"合計 {len(df)} 件")
        else:
            st.warning("いずれのURLからも物件が取得できませんでした。")

    with tab_master:
        st.markdown(
            """
            **候補駅リスト（CSV）** をアップロードし、到着地のボタンを押すと、Yahoo!乗換案内で  
            **到着 8:30** の条件で検索し、**検索結果のうち最も短い所要時間** を取得してマスタCSVを出力します。  
            スクレイピング結果の「最寄り駅」列を抽出したCSVをそのまま使えます。
            """
        )
        station_list_file = st.file_uploader(
            "候補駅リストCSVをアップロード",
            type=["csv"],
            key="station_list",
            help="列に「駅名」または「最寄り駅」を含むCSV。1列だけのCSVでも可。UTF-8 / Shift_JIS 対応。",
        )
        delay_sec = st.slider("駅ごとの取得間隔（秒）", min_value=1.0, max_value=5.0, value=2.0, step=0.5)
        st.caption("到着 8:30 で検索し、表示された経路のうち最短の所要時間を採用します。")
        col_s, col_t, col_th, col_u = st.columns(4)
        with col_s:
            get_times_shimbashi_btn = st.button("新橋までの所要時間を取得", type="primary", key="get_shimbashi")
        with col_t:
            get_times_toranomon_btn = st.button("虎ノ門までの所要時間を取得", type="primary", key="get_toranomon")
        with col_th:
            get_times_toranomon_hills_btn = st.button("虎ノ門ヒルズまでの所要時間を取得", type="primary", key="get_toranomon_hills")
        with col_u:
            get_times_uchisaiwaicho_btn = st.button("内幸町までの所要時間を取得", type="primary", key="get_uchisaiwaicho")

    # 到着地ごとのラベル（表示名, 列名, ダウンロードファイル名）
    _destinations = [
        (get_times_shimbashi_btn, "新橋", "新橋まで所要時間(分)", "station_time_to_shimbashi_master.csv"),
        (get_times_toranomon_btn, "虎ノ門", "虎ノ門まで所要時間(分)", "station_time_to_toranomon_master.csv"),
        (get_times_toranomon_hills_btn, "虎ノ門ヒルズ", "虎ノ門ヒルズまで所要時間(分)", "station_time_to_toranomon_hills_master.csv"),
        (get_times_uchisaiwaicho_btn, "内幸町", "内幸町まで所要時間(分)", "station_time_to_uchisaiwaicho_master.csv"),
    ]
    _clicked = next((d for clicked, *d in _destinations if clicked), None)

    if _clicked:
        dest_name, col_name, file_name = _clicked
        if station_list_file is None:
            st.error("候補駅リストのCSVをアップロードしてください。")
        else:
            station_list_file.seek(0)
            try:
                station_df = pd.read_csv(station_list_file, encoding="utf-8")
            except Exception:
                station_list_file.seek(0)
                station_df = pd.read_csv(station_list_file, encoding="cp932")
            station_df.columns = [c.strip() for c in station_df.columns]
            station_col = None
            for c in ["駅名", "最寄り駅"]:
                if c in station_df.columns:
                    station_col = c
                    break
            if station_col is None:
                st.error("CSVに「駅名」または「最寄り駅」列を含めてください。")
            else:
                stations = station_df[station_col].dropna().astype(str).str.strip().unique().tolist()
                stations = [s for s in stations if s]
                if not stations:
                    st.error("有効な駅名が1件もありません。")
                else:
                    st.info(f"到着 {ARRIVE_HOUR}:{ARRIVE_MINUTE:02d} で、各駅 → {dest_name} の最短所要時間を取得します（{len(stations)} 駅）。")
                    progress = st.progress(0, text="0件目")
                    status = st.empty()
                    result_dict: Dict[str, Optional[int]] = {}
                    for i, station in enumerate(stations):
                        status.info(f"({i+1}/{len(stations)}) {station} → {dest_name} を検索中…")
                        progress.progress((i + 1) / len(stations), text=f"{i+1}/{len(stations)} 件目")
                        result_dict[station] = fetch_time_to_station(station, dest_name)
                        time.sleep(delay_sec)
                    progress.progress(1.0, text="完了")
                    status.empty()
                    master_df = pd.DataFrame([
                        {"駅名": s, col_name: result_dict[s]} for s in stations
                    ])
                    st.subheader(f"所要時間マスタ（→ {dest_name}）")
                    st.dataframe(master_df, use_container_width=True)
                    csv_master = master_df.to_csv(index=False).encode("utf-8-sig")
                    st.download_button(
                        label="マスタCSVをダウンロード",
                        data=csv_master,
                        file_name=file_name,
                        mime="text/csv",
                        key="dl_master_" + dest_name,
                    )
                    ok = sum(1 for v in result_dict.values() if v is not None)
                    st.info(f"取得できた駅: {ok} / {len(stations)} 件。未取得の駅は手動で乗換案内を確認してください。")


if __name__ == "__main__":
    main()

