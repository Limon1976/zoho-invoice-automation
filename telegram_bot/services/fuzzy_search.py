from __future__ import annotations

from typing import List, Dict, Any, Optional
from rapidfuzz import fuzz, process


def best_company_match(name: str, candidates: List[Dict[str, Any]], key: str = 'contact_name', threshold: int = 90) -> Optional[Dict[str, Any]]:
    if not name or not candidates:
        return None
    choices = [(c.get(key) or '', idx) for idx, c in enumerate(candidates)]
    if not choices:
        return None
    result = process.extractOne(name, [c[0] for c in choices], scorer=fuzz.token_sort_ratio)
    if not result:
        return None
    score, idx = result[1], result[2]
    if score >= threshold:
        return candidates[idx]
    return None


