"""
SUUMO 新着物件バッチのエントリポイント。
設定・URLリスト読み込み → スクレイピング → 所要時間突合 → スコアリング → 新着判定 → 一覧HTML生成 → 既知更新 → メール送信。
"""
import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from batch import scraper, station_time, storage, extractor, mailer, properties_list

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_URL_LIST = "./docs/suumo_url_list.csv"
DEFAULT_EXTRACTION_CONDITIONS = "./docs/extraction_conditions.yaml"
DEFAULT_STATION_TIME = "./station_time.xlsx"
DEFAULT_KNOWN_PROPERTIES = "./data/known_properties.json"
DEFAULT_PROPERTIES_LIST_HTML = "./docs/properties_list.html"


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    path = config_path or "config.yaml"
    cfg = {
        "url_list_path": DEFAULT_URL_LIST,
        "extraction_conditions_path": DEFAULT_EXTRACTION_CONDITIONS,
        "station_time_master_path": DEFAULT_STATION_TIME,
        "known_properties_path": DEFAULT_KNOWN_PROPERTIES,
        "properties_list_html_path": DEFAULT_PROPERTIES_LIST_HTML,
        "delay_seconds": 1.0,
    }
    if Path(path).exists():
        with open(path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
            cfg.update(loaded)
    # 環境変数で上書き
    for key in ["smtp_host", "smtp_port", "smtp_user", "smtp_pass", "from_email"]:
        env_key = key.upper()
        if os.environ.get(env_key):
            cfg[key] = os.environ[env_key]
    if os.environ.get("TO_EMAILS"):
        cfg["to_emails"] = [e.strip() for e in os.environ["TO_EMAILS"].split(",") if e.strip()]
    elif "to_emails" not in cfg:
        cfg["to_emails"] = []
    if os.environ.get("PROPERTIES_LIST_PAGE_URL"):
        cfg["properties_list_page_url"] = os.environ["PROPERTIES_LIST_PAGE_URL"]
    if cfg.get("smtp_port") is not None:
        cfg["smtp_port"] = int(cfg["smtp_port"])
    return cfg


def load_url_list(path: str) -> List[Dict[str, str]]:
    """CSV を読み、種別・都道府県・URL の行リストを返す。"""
    p = Path(path)
    if not p.exists():
        logger.error("URLリストが存在しません: %s", path)
        sys.exit(1)
    for enc in ["utf-8-sig", "utf-8", "cp932"]:
        try:
            df = pd.read_csv(p, encoding=enc)
            break
        except Exception:
            continue
    else:
        logger.error("URLリストを読み込めません: %s", path)
        sys.exit(1)
    df.columns = [str(c).strip() for c in df.columns]
    if "URL" not in df.columns and "url" in df.columns:
        df["URL"] = df["url"]
    # 列名が文字化けしている場合、先頭3列を 種別・都道府県・URL として扱う
    if "種別" not in df.columns and len(df.columns) >= 3:
        df = df.rename(columns={df.columns[0]: "種別", df.columns[1]: "都道府県", df.columns[2]: "URL"})
    for col in ["種別", "都道府県", "URL"]:
        if col not in df.columns:
            logger.error("URLリストに「種別」「都道府県」「URL」列が必要です: %s (読み取れた列: %s)", path, list(df.columns))
            sys.exit(1)
    df = df[["種別", "都道府県", "URL"]].dropna(subset=["URL"])
    df = df[df["URL"].astype(str).str.contains("suumo.jp", na=False)]
    return df.to_dict("records")


def main() -> None:
    parser = argparse.ArgumentParser(description="SUUMO 新着物件バッチ")
    parser.add_argument("--config", default="config.yaml", help="設定ファイルのパス")
    parser.add_argument("--dry-run", action="store_true", help="DB書き込み・メール送信を行わない")
    args = parser.parse_args()

    config = load_config(args.config)
    url_list_path = config.get("url_list_path") or DEFAULT_URL_LIST
    extraction_path = config.get("extraction_conditions_path") or DEFAULT_EXTRACTION_CONDITIONS
    station_time_path = config.get("station_time_master_path") or DEFAULT_STATION_TIME
    known_path = config.get("known_properties_path") or DEFAULT_KNOWN_PROPERTIES
    list_html_path = config.get("properties_list_html_path") or DEFAULT_PROPERTIES_LIST_HTML
    delay_seconds = float(config.get("delay_seconds", 1.0))

    if not Path(extraction_path).exists():
        logger.error("抽出条件ファイルが存在しません: %s", extraction_path)
        sys.exit(1)

    url_list = load_url_list(url_list_path)
    known = storage.load_known_properties(known_path)
    station_times = station_time.load_station_time_master(station_time_path)
    conditions = extractor.load_conditions(extraction_path)
    threshold = extractor.get_threshold(conditions)

    logger.info("検索URL数: %s, 既知物件数: %s, 閾値: %s", len(url_list), len(known), threshold)

    # スクレイピング（全URL）
    all_props: List[Dict[str, Any]] = []
    for row in url_list:
        records = scraper.scrape_url_list([row], delay_seconds=delay_seconds)
        for r in records:
            # 所要時間マスタで突合
            station = r.get("nearest_station")
            walk = r.get("walk_minutes") or 0
            rec = station_times.get(station) if station else None
            if rec:
                time_work = rec.get("time")
                r["time_to_workplace"] = time_work
                r["first_train_score"] = rec.get("first_train_score", 0)
                r["neighborhood_score"] = rec.get("neighborhood_score", 0)
            else:
                r["time_to_workplace"] = None
                r["first_train_score"] = 0
                r["neighborhood_score"] = 0
            r["total_time"] = (
                (r["time_to_workplace"] + walk)
                if (r["time_to_workplace"] is not None and walk is not None)
                else r["time_to_workplace"]
            )
            all_props.append(r)

    logger.info("取得件数: %s", len(all_props))

    # スコアリングと閾値以上のみ
    above_threshold: List[Dict[str, Any]] = []
    for p in all_props:
        score = extractor.score_property(p, conditions)
        if extractor.passes_threshold(score, conditions):
            p["extraction_score"] = round(score, 2)
            above_threshold.append(p)

    logger.info("閾値以上: %s 件", len(above_threshold))

    # 新着判定
    new_listings: List[Dict[str, Any]] = []
    for p in above_threshold:
        pid = p.get("property_id")
        if not pid:
            continue
        if storage.find_by_property_id(known, pid):
            continue
        if storage.find_duplicate(known, p):
            continue
        rec = storage.to_stored_record(p, p.get("extraction_score"))
        known.append(rec)
        new_listings.append(rec)

    # 全物件一覧は「今回の検索で閾値以上の全件」（above_threshold）
    if not args.dry_run:
        storage.save_known_properties(known_path, known)
        properties_list.generate_properties_list_html(above_threshold, list_html_path)
        logger.info("全物件一覧を出力: %s", list_html_path)

        list_page_url = config.get("properties_list_page_url", "")
        to_emails = config.get("to_emails") or []
        if new_listings:
            send_ok = mailer.send_new_listings_email(
                new_listings,
                list_page_url or None,
                smtp_host=config.get("smtp_host", ""),
                smtp_port=int(config.get("smtp_port", 587)),
                smtp_user=config.get("smtp_user", ""),
                smtp_pass=config.get("smtp_pass", ""),
                from_email=config.get("from_email", ""),
                to_emails=to_emails,
            )
            if not send_ok:
                logger.warning("メール送信に失敗しました")
        else:
            if to_emails:
                send_ok = mailer.send_no_new_listings_email(
                    len(above_threshold),
                    list_page_url or None,
                    smtp_host=config.get("smtp_host", ""),
                    smtp_port=int(config.get("smtp_port", 587)),
                    smtp_user=config.get("smtp_user", ""),
                    smtp_pass=config.get("smtp_pass", ""),
                    from_email=config.get("from_email", ""),
                    to_emails=to_emails,
                )
                if not send_ok:
                    logger.warning("メール送信に失敗しました")
            else:
                logger.info("新着なし・送信先未設定のためメール送信しません")
    else:
        logger.info("--dry-run のため保存・メール送信は行いません。新着: %s 件", len(new_listings))

    logger.info("完了. 新着: %s 件", len(new_listings))


if __name__ == "__main__":
    main()
