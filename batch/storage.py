"""
既知物件一覧（known_properties.json）の読み書きと重複判定。
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 重複判定に使うキー（価格・建物面積・住所は必須）
DUPLICATE_KEYS = ["price_min", "price_max", "building_area", "address"]


def load_known_properties(path: str) -> List[Dict[str, Any]]:
    """
    known_properties.json を読み込む。ファイルが無い・空の場合は空リストを返す。
    """
    p = Path(path)
    if not p.exists():
        return []
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("既知物件一覧の読み込みに失敗しました: %s - %s（空で開始します）", path, e)
        return []


def save_known_properties(path: str, records: List[Dict[str, Any]]) -> None:
    """既知物件一覧をJSONで保存する。"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def find_by_property_id(known: List[Dict[str, Any]], property_id: str) -> Optional[Dict[str, Any]]:
    """property_id で既知一覧から検索。"""
    for r in known:
        if r.get("property_id") == property_id:
            return r
    return None


def find_duplicate(
    known: List[Dict[str, Any]],
    candidate: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    価格・建物面積・住所が完全一致する既存レコードがあれば返す（別IDの同一物件判定）。
    """
    for r in known:
        if _same_duplicate_key_values(r, candidate):
            return r
    return None


def _same_duplicate_key_values(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    for key in DUPLICATE_KEYS:
        va = a.get(key)
        vb = b.get(key)
        if va is None and vb is None:
            continue
        if va is None or vb is None:
            return False
        if key in ("price_min", "price_max", "building_area"):
            try:
                if float(va) != float(vb):
                    return False
            except (TypeError, ValueError):
                return False
        else:
            if str(va).strip() != str(vb).strip():
                return False
    return True


def to_stored_record(prop: Dict[str, Any], extraction_score: Optional[float] = None) -> Dict[str, Any]:
    """
    スクレイピング結果の1件を既知一覧用の保存形式に変換する。
    first_seen_at, created_at を付与。extraction_score を付与。
    """
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    r = dict(prop)
    r["first_seen_at"] = now
    r["created_at"] = now
    if extraction_score is not None:
        r["extraction_score"] = round(extraction_score, 2)
    return r


def add_new_and_collect_new_ids(
    known: List[Dict[str, Any]],
    new_records: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[str]]:
    """
    新規レコードを既知一覧に追加し、追加した property_id のリストを返す。
    known は破壊的に更新される。返り値は (更新後の known, 新規追加した id のリスト)。
    """
    added_ids: List[str] = []
    for rec in new_records:
        pid = rec.get("property_id")
        if not pid:
            continue
        if find_by_property_id(known, pid):
            continue
        known.append(rec)
        added_ids.append(pid)
    return known, added_ids
