from __future__ import annotations

from typing import Optional, Tuple, Dict, Any
import re


def _detect_expected_country(supplier_country: Optional[str], extracted_text: Optional[str]) -> Optional[str]:
    country_raw = (supplier_country or '').strip().lower()
    iso_map = {
        'poland': 'PL', 'polska': 'PL', 'estonia': 'EE', 'eesti': 'EE', 'germany': 'DE',
        'deutschland': 'DE', 'latvia': 'LV', 'lithuania': 'LT', 'netherlands': 'NL',
        'ireland': 'IE', 'france': 'FR', 'spain': 'ES', 'italy': 'IT', 'portugal': 'PT',
        'sweden': 'SE', 'denmark': 'DK', 'united kingdom': 'GB', 'uk': 'GB'
    }
    expected = iso_map.get(country_raw)
    if not expected and extracted_text and re.search(r"\bNIP\b", extracted_text, re.IGNORECASE):
        expected = 'PL'
    return expected


def _build_target_vat(vat_candidate: Optional[str], supplier_country: Optional[str], extracted_text: Optional[str]) -> Optional[str]:
    from src.domain.services.vat_validator import VATValidatorService
    candidate = (vat_candidate or '').strip()
    if not candidate and extracted_text:
        m = re.search(r"\bNIP\s*[:#]?\s*(\d{10})\b", extracted_text, re.IGNORECASE)
        if m:
            candidate = m.group(1)
    if not candidate:
        return None
    vvs = VATValidatorService()
    expected = _detect_expected_country(supplier_country, extracted_text)
    check = vvs.validate_vat(candidate, expected_country=expected)
    if check.is_valid:
        return vvs.add_country_prefix(check.vat_number.value, check.country_code).replace(' ', '')
    # keep provided prefix if any; otherwise digits only
    if len(candidate) >= 2 and candidate[:2].isalpha():
        return candidate.replace(' ', '')
    digits = ''.join(ch for ch in candidate if ch.isdigit())
    return digits or candidate


async def force_update_vat(
    zoho_client,
    org_id: str,
    contact_id: str,
    vat_candidate: Optional[str],
    supplier_country: Optional[str],
    extracted_text: Optional[str]
) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """Unifies VAT update flow via custom_fields by api_name with verification.

    Returns: (applied, target_vat, debug_info)
    """
    target_vat = _build_target_vat(vat_candidate, supplier_country, extracted_text)
    debug: Dict[str, Any] = {'target_vat': target_vat}
    if not target_vat:
        return False, None, debug

    url = f'https://www.zohoapis.eu/books/v3/contacts/{contact_id}?organization_id={org_id}'
    vat_cf_api = 'cf_tax_id' if org_id == '20082562863' else 'cf_vat_id'
    payload_api = {"custom_fields": [{"api_name": vat_cf_api, "value": target_vat}]}
    try:
        resp = await zoho_client._make_request('PUT', url, json=payload_api)
        debug['resp_api'] = resp
    except Exception as e:
        debug['error_api'] = str(e)
        resp = None

    # verify
    try:
        latest = await zoho_client.get_contact_details(org_id, contact_id) or {}
    except Exception:
        latest = {}
    values = set()
    for k in ['cf_tax_id', 'cf_vat_id']:
        if latest.get(k):
            values.add(str(latest.get(k)))
    for cf in (latest.get('custom_fields') or []):
        v = (cf.get('value') or '').strip()
        if v:
            values.add(v)
    applied = target_vat in values or (
        len(target_vat) > 2 and target_vat[:2].isalpha() and any((len(v) > 2 and v[:2].isalpha() and v[2:] == target_vat[2:]) for v in values)
    )
    debug['verify_values'] = list(values)
    return applied, target_vat, debug


q