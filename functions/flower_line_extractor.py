from __future__ import annotations

import re
from typing import List, Dict, Any


def extract_flower_lines_from_ocr(ocr_text: str) -> List[Dict[str, Any]]:
    """Best‑effort parser for Polish flower invoices (HIBISPOL layout).

    Extracts rows with fields: name, quantity, unit_price (gross if inclusive), tax_percent.
    Heuristics:
    - Scan windowed text; a row is identified when we see "<qty> szt" near numbers
    - The product name is the nearest non-empty preceding line with letters, skipping service words
    - VAT percent taken from the same window (8%/23%), default 8 if unclear
    - Unit price: prefer the first X,XX number in the window; caller will convert to net/gross
    """

    if not ocr_text:
        return []

    lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]
    results: List[Dict[str, Any]] = []
    seen_keys: set[tuple[str, float]] = set()

    skip_re = re.compile(r"^(Strona|Page|Razem|RAZEM|IBAN|Numer rachunku|Wileńska|Odebrał|Zestawienie|Netto|Brutto|Kwota VAT|Wartość|Sprzedawca|Nabywca|NIP|REGON|Tel\.|VAT$)", re.I)

    i = 0
    row_start_re = re.compile(r"^(\d{1,3})\s+(.+)")  # e.g. "1 Dahl Karma Prospero"
    num_only_re = re.compile(r"^\d{1,4}(?:[\.,]\d+)?$")
    price_re = re.compile(r"(\d{1,3}[\.,]\d{2})")

    while i < len(lines):
        line = lines[i]
        if skip_re.search(line) or line.lower() == 'szt':
            i += 1
            continue

        m_row = row_start_re.match(line)
        if not m_row:
            i += 1
            continue

        name = m_row.group(2).strip()
        qty = None
        unit_price = None
        tax_percent = 8 if not re.search(r"\bruscus\b", name, re.I) else 23

        # scan next 10 lines to pick quantity, unit, price and VAT
        window_lines = lines[i+1:i+11]
        for wl in window_lines:
            if qty is None and (num_only_re.match(wl) and ' ' not in wl):
                # standalone integer/decimal -> candidate for qty; next line often 'szt'
                try:
                    qv = float(wl.replace(',', '.'))
                    if qv.is_integer():
                        qty = qv
                        continue
                except Exception:
                    pass
            if unit_price is None:
                mp = price_re.search(wl)
                if mp:
                    try:
                        pv = float(mp.group(1).replace(',', '.'))
                        # отбрасываем большие суммы (скорее "Wartość brutto")
                        if pv < 100:  # разумная цена за штуку
                            unit_price = pv
                    except Exception:
                        pass
            if '23%' in wl:
                tax_percent = 23
            elif '8%' in wl:
                tax_percent = 8

        if qty is not None and unit_price is not None:
            key = (re.sub(r"\s+", " ", name)[:100].lower(), qty)
            if key not in seen_keys:
                results.append({
                    "name": name,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "tax_percent": tax_percent,
                })
                seen_keys.add(key)

        # advance to next potential row
        i += 1

    return results


# --- User-provided robust parsing tailored for HIBISPOL layout ---
import re


def better_split_items_safe(text: str) -> List[str]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    entries: List[str] = []
    current_block = ""
    for line in lines:
        if re.match(r"^\d{1,2}\s+[A-Za-z]", line):
            if current_block.strip():
                entries.append(current_block.strip())
                current_block = ""
        current_block += line + " "
    if current_block.strip():
        entries.append(current_block.strip())
    return entries


def parse_item_block(block: str) -> Dict[str, Any]:
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    block_flat = " ".join(lines).strip()

    name_match = re.match(r"^\d{1,2}\s+(.*?)\s+\d+\s*szt", block_flat)
    name = name_match.group(1).strip() if name_match else block_flat

    qty_match = re.search(r"(\d+)\s*szt", block_flat)
    if not qty_match:
        return {"name": name, "error": "Qty/unit not found"}
    quantity = int(qty_match.group(1))

    numbers = re.findall(r"\d+[,\.]\d+", block_flat)
    nums: List[float] = []
    for n in numbers:
        try:
            nums.append(float(n.replace(",", ".")))
        except Exception:
            continue

    if len(nums) < 4:
        return {"name": name, "quantity": quantity, "error": f"Not enough numbers: {nums}"}

    vat_percent = 23 if re.search(r"23%", block_flat) else 8

    return {
        "name": name,
        "quantity": quantity,
        "unit": "szt",
        "unit_price_netto": nums[0],
        "netto_total": nums[1],
        "vat_percent": vat_percent,
        "vat_amount": nums[2],
        "brutto_total": nums[3],
    }


def parse_invoice_items(raw_text: str) -> List[Dict[str, Any]]:
    blocks = better_split_items_safe(raw_text or "")
    parsed = [parse_item_block(b) for b in blocks]
    # Оставляем только валидные без error
    cleaned: List[Dict[str, Any]] = []
    for p in parsed:
        if p and not p.get("error") and p.get("quantity") and (p.get("unit_price_netto") or p.get("brutto_total")):
            cleaned.append(p)
    return cleaned


