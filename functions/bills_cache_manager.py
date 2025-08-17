import os
import json
from datetime import datetime
from typing import Optional, List, Dict

from .zoho_api import get_bills, get_bill_details


def _cache_path(org_id: str) -> str:
    os.makedirs("data/optimized_cache", exist_ok=True)
    return f"data/optimized_cache/zoho_bills_{org_id}.json"


def load_bills_cache(org_id: str) -> Dict:
    path = _cache_path(org_id)
    if not os.path.exists(path):
        return {"org_id": org_id, "updated_at": None, "bills": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"org_id": org_id, "updated_at": None, "bills": []}


def save_bills_cache(org_id: str, cache: Dict) -> None:
    path = _cache_path(org_id)
    cache["org_id"] = org_id
    cache["updated_at"] = datetime.utcnow().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def refresh_bills_cache(org_id: str, base_year: Optional[int] = None, base_month: Optional[int] = None, months_back: int = 12) -> Dict:
    """
    Обновляет кэш счетов, сканируя месяцы назад от заданной даты (или текущей)
    и сохраняя минимальные данные: bill_number, bill_id, year, month.
    """
    now = datetime.utcnow()
    if base_year is None or base_month is None:
        base_year, base_month = now.year, now.month

    def add_month(year: int, month: int, delta: int) -> (int, int):
        idx = (year * 12 + (month - 1)) + delta
        y = idx // 12
        m = (idx % 12) + 1
        return y, m

    cache = {"org_id": org_id, "updated_at": None, "bills": []}
    seen_ids = set()

    for d in range(0, months_back + 1):
        y, m = add_month(base_year, base_month, -d)
        try:
            month_bills = get_bills(org_id, y, m)
        except Exception:
            continue
        for bn, bid, _ha, _aid in month_bills:
            if bid in seen_ids:
                continue
            cache["bills"].append({
                "bill_number": bn,
                "bill_id": bid,
                "year": y,
                "month": m,
            })
            seen_ids.add(bid)

    save_bills_cache(org_id, cache)
    return cache


def _normalize(s: str) -> str:
    return "".join(ch for ch in s.upper() if ch.isalnum())


def _digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def _lead_letters(s: str) -> str:
    import re
    m = re.match(r"^[A-Za-z]+", s.strip())
    return (m.group(0) if m else "").upper()


def _normalize_confusables(s: str) -> str:
    table = str.maketrans({
        'I': '1', 'L': '1', '|': '1',
        'O': '0', 'Q': '0',
        'B': '8'
    })
    return _normalize(s.translate(table))


def find_bill_candidates_in_cache(org_id: str, bill_number: str) -> List[Dict]:
    cache = load_bills_cache(org_id)
    norm_target = _normalize(bill_number)
    digits_target = _digits(bill_number)
    prefix_target = _lead_letters(bill_number)

    candidates = []
    for entry in cache.get("bills", []):
        bn = entry.get("bill_number") or ""
        bn_norm = _normalize(bn)
        bn_digits = _digits(bn)
        bn_prefix = _lead_letters(bn)
        if bn_norm == norm_target or _normalize_confusables(bn) == _normalize_confusables(bill_number):
            candidates.append(entry)
        elif digits_target and bn_digits and digits_target == bn_digits:
            if (not prefix_target or not bn_prefix) or (prefix_target == bn_prefix):
                candidates.append(entry)
    return candidates


def ensure_bills_cache(org_id: str, document_date: Optional[str] = None) -> Dict:
    cache = load_bills_cache(org_id)
    # Обновляем если пустой или старше 7 дней
    try:
        if not cache.get("bills"):
            raise ValueError("empty")
        if not cache.get("updated_at"):
            raise ValueError("no updated_at")
        updated = datetime.fromisoformat(cache["updated_at"])
        if (datetime.utcnow() - updated).days > 7:
            raise ValueError("stale")
        return cache
    except Exception:
        pass

    # Определяем базовый год/месяц для более точной выборки
    base_year = base_month = None
    if document_date:
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                dt = datetime.strptime(document_date.strip(), fmt)
                base_year, base_month = dt.year, dt.month
                break
            except Exception:
                continue

    return refresh_bills_cache(org_id, base_year, base_month, months_back=14)


