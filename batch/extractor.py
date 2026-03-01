"""
抽出条件（extraction_conditions.yaml）の読み込みとスコアリング。
閾値以上だった物件のみを抽出対象とする。
"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


def load_conditions(path: str) -> Dict[str, Any]:
    """extraction_conditions.yaml を読み込む。"""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def score_property(prop: Dict[str, Any], conditions: Dict[str, Any]) -> float:
    """
    物件レコードに抽出条件を適用し、合計スコアを返す。
    取得できない項目は 0 点として扱う。
    """
    total = 0.0

    # 価格（都道府県別）
    price_cfg = conditions.get("price") or {}
    prefecture = (prop.get("prefecture") or "").strip()
    table = price_cfg.get(prefecture) or price_cfg.get("default") or []
    price_val = _num(prop.get("price_min")) or _num(prop.get("price_max"))
    if price_val is not None and table:
        total += _score_by_max_value(price_val, table, "max_price")

    # 建物面積
    area_cfg = conditions.get("building_area") or []
    area = _num(prop.get("building_area"))
    if area is not None and area_cfg:
        total += _score_by_min_value(area, area_cfg, "min_area")

    # 駅徒歩
    walk_cfg = conditions.get("walk_to_station") or []
    walk = _int(prop.get("walk_minutes"))
    if walk is not None and walk_cfg:
        total += _score_by_max_value(walk, walk_cfg, "max_minutes")

    # 最寄り～職場（total_time または time_to_workplace + walk_minutes）
    station_cfg = conditions.get("station_to_workplace") or []
    time_work = _int(prop.get("time_to_workplace"))
    total_time = _int(prop.get("total_time"))
    ttl = total_time if total_time is not None else (
        (time_work + walk) if (time_work is not None and walk is not None) else time_work
    )
    if ttl is not None and station_cfg:
        total += _score_by_max_value(ttl, station_cfg, "max_minutes")

    # 乗換回数（一覧では取得できないため 0）
    transfers_cfg = conditions.get("transfers") or []
    transfers = _int(prop.get("transfers"))
    if transfers is not None and transfers_cfg:
        total += _score_by_max_value(transfers, transfers_cfg, "max_transfers")

    # 築年数
    built_cfg = conditions.get("built_year") or {}
    built = (prop.get("built_year") or "").strip()
    if built:
        if built == "新築" or (built_cfg and built_cfg.get("new") is not None):
            total += float(built_cfg.get("new", 0))
        # TODO: 年数パースで years_old マッピング

    # 始発・階数（一覧では取得できないため 0）
    first_cfg = conditions.get("first_train") or {}
    if first_cfg and prop.get("first_train"):
        total += float(first_cfg.get("yes", 0))
    floors_cfg = conditions.get("floors") or {}
    if floors_cfg and prop.get("floors"):
        total += float(floors_cfg.get(prop["floors"], 0))

    return total


def _score_by_max_value(value: float, table: List[Dict], key: str) -> float:
    """value が key 以下となる最初のエントリの score を返す。昇順で並んでいる想定。"""
    for entry in sorted(table, key=lambda x: x.get(key, 0)):
        if value <= entry.get(key, 0):
            return float(entry.get("score", 0))
    return 0.0


def _score_by_min_value(value: float, table: List[Dict], key: str) -> float:
    """value が key 以上となる最初のエントリの score を返す。降順で並んでいる想定。"""
    for entry in sorted(table, key=lambda x: -x.get(key, 0)):
        if value >= entry.get(key, 0):
            return float(entry.get("score", 0))
    return 0.0


def _num(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v) -> Optional[int]:
    n = _num(v)
    return int(n) if n is not None else None


def get_threshold(conditions: Dict[str, Any]) -> float:
    """閾値を返す。"""
    return float(conditions.get("threshold", 0))


def passes_threshold(score: float, conditions: Dict[str, Any]) -> bool:
    """スコアが閾値以上なら True。"""
    return score >= get_threshold(conditions)
