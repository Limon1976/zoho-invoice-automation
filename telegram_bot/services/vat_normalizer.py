from __future__ import annotations

from typing import Optional
import regex as re
from unidecode import unidecode

try:
    from stdnum.eu import vat as eu_vat
except Exception:  # pragma: no cover
    eu_vat = None
try:
    from stdnum.pl import nip as pl_nip
except Exception:  # pragma: no cover
    pl_nip = None


COUNTRY_TO_ISO = {
    'poland': 'PL', 'polska': 'PL',
    'estonia': 'EE', 'eesti': 'EE',
    'germany': 'DE', 'deutschland': 'DE',
    'latvia': 'LV', 'lithuania': 'LT', 'netherlands': 'NL',
    'ireland': 'IE', 'france': 'FR', 'spain': 'ES', 'italy': 'IT',
    'portugal': 'PT', 'sweden': 'SE', 'denmark': 'DK',
    'united kingdom': 'GB', 'uk': 'GB'
}


def expected_iso_from_context(supplier_country: Optional[str], extracted_text: Optional[str]) -> Optional[str]:
    country = (supplier_country or '').strip().lower()
    iso = COUNTRY_TO_ISO.get(country)
    if not iso and extracted_text and re.search(r"\bNIP\b", extracted_text, flags=re.IGNORECASE):
        return 'PL'
    return iso


def extract_digits_candidate(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"\bNIP\s*[:#]?\s*(\d{10})\b", text, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    # generic EU VAT like PL123..., DE123...
    m2 = re.search(r"\b([A-Z]{2})\s*([0-9]{8,14})\b", unidecode(text).upper())
    if m2:
        return f"{m2.group(1)}{m2.group(2)}"
    return None


def normalize_vat(raw_vat: Optional[str], supplier_country: Optional[str], extracted_text: Optional[str]) -> Optional[str]:
    raw = (raw_vat or '').strip()
    if not raw:
        raw = extract_digits_candidate(extracted_text or '') or ''
    if not raw:
        return None

    raw_u = unidecode(raw).replace(' ', '')
    iso = expected_iso_from_context(supplier_country, extracted_text)

    # already looks like EU VAT with prefix
    if len(raw_u) >= 2 and raw_u[:2].isalpha() and raw_u[2:].isdigit():
        try:
            if eu_vat:
                eu_vat.validate(raw_u)
                return raw_u
        except Exception:
            pass
        return raw_u

    # pure digits path (e.g., NIP)
    digits = ''.join(ch for ch in raw_u if ch.isdigit())
    if iso == 'PL' and pl_nip and len(digits) == 10:
        try:
            pl_nip.validate(digits)
            return f"PL{digits}"
        except Exception:
            return f"PL{digits}"

    if iso and digits:
        return f"{iso}{digits}"

    # last resort
    return raw_u or None


