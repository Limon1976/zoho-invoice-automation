from __future__ import annotations

from typing import Optional, Dict, Any, Tuple
import re


def _iso_from_country(country: Optional[str]) -> Optional[str]:
    m = {
        'poland': 'PL', 'polska': 'PL',
        'estonia': 'EE', 'eesti': 'EE',
        'germany': 'DE', 'deutschland': 'DE',
        'latvia': 'LV', 'lithuania': 'LT', 'netherlands': 'NL',
        'ireland': 'IE', 'france': 'FR', 'spain': 'ES', 'italy': 'IT',
        'portugal': 'PT', 'sweden': 'SE', 'denmark': 'DK',
        'united kingdom': 'GB', 'uk': 'GB'
    }
    if not country:
        return None
    return m.get(country.strip().lower())


def build_doc_vat(raw_vat: Optional[str], supplier_country: Optional[str], extracted_text: Optional[str], our_company: Optional[str]) -> Optional[str]:
    """Return VAT with ISO prefix when possible (e.g., PL1182241766)."""
    from src.domain.services.vat_validator import VATValidatorService
    raw = (raw_vat or '').strip()
    if not raw and extracted_text:
        m = re.search(r"\bNIP\s*[:#]?\s*(\d{10})\b", extracted_text, re.IGNORECASE)
        if m:
            raw = m.group(1)

    # choose country
    country = (supplier_country or '').strip()
    if not country and our_company:
        oc = our_company.lower()
        if 'parkentertainment' in oc:
            country = 'Poland'
        elif 'tavie' in oc:
            country = 'Estonia'

    v = VATValidatorService()
    valid = v.validate_vat(raw, expected_country=country or None)
    if valid.is_valid:
        return v.add_country_prefix(valid.vat_number.value, valid.country_code).replace(' ', '')

    digits = ''.join(ch for ch in raw if ch.isdigit())
    pref = _iso_from_country(country)
    if pref and digits:
        return f"{pref}{digits}"
    return raw or None


def _trim_100(value: Any) -> Any:
    if isinstance(value, str):
        return value[:100]
    if isinstance(value, list):
        return [_trim_100(v) for v in value]
    if isinstance(value, dict):
        return {k: _trim_100(v) for k, v in value.items()}
    return value


async def _resolve_vat_customfield_id(zoho_client, org_id: str, contact_id: str, vat_api: str) -> Optional[str]:
    try:
        details = await zoho_client.get_contact_details(org_id, contact_id) or {}
        for cf in (details.get('custom_fields') or []):
            api = (cf.get('api_name') or '').strip()
            label = (cf.get('label') or cf.get('field_label') or '').strip().lower()
            if api == vat_api or label in {'tax id', 'vat', 'vat id', 'vat number'}:
                if cf.get('customfield_id'):
                    return cf['customfield_id']
    except Exception:
        pass
    return None


async def update_supplier_contact(
    zoho_client,
    org_id: str,
    contact_id: str,
    analysis: Dict[str, Any],
) -> Tuple[bool, bool, Optional[str]]:
    """Refactored updater: returns (vat_applied, other_applied, doc_vat)."""
    # Build doc_vat once
    doc_vat = build_doc_vat(
        analysis.get('supplier_vat'),
        analysis.get('supplier_country'),
        analysis.get('extracted_text'),
        analysis.get('our_company'),
    )

    url = f"https://www.zohoapis.eu/books/v3/contacts/{contact_id}?organization_id={org_id}"
    vat_applied = False
    other_applied = False

    # 1) VAT first
    if doc_vat:
        vat_api = 'cf_tax_id' if org_id == '20082562863' else 'cf_vat_id'
        cf_id = await _resolve_vat_customfield_id(zoho_client, org_id, contact_id, vat_api)
        if cf_id:
            vat_payload = {"custom_fields": [{"customfield_id": cf_id, "value": doc_vat}]}
        else:
            vat_payload = {"custom_fields": [{"api_name": vat_api, "value": doc_vat}]}
        resp = await zoho_client._make_request('PUT', url, json=_trim_100(vat_payload))
        vat_applied = bool(resp and (resp.get('code') == 0 or resp.get('contact')))

    # 2) Other fields
    update_data: Dict[str, Any] = {}
    # phone
    try:
        from functions.phone_parser import parse_phone_number
        phone_raw = (analysis.get('supplier_phone') or '').strip()
        if phone_raw:
            p = parse_phone_number(phone_raw)
            if p.get('national_format'):
                update_data['phone'] = p['national_format'][:20]
            if p.get('country_calling_code'):
                code = str(p['country_calling_code'])
                update_data['phone_code'] = code
                update_data['phone_country_code'] = code
    except Exception:
        pass

    # address
    if any([analysis.get('supplier_street'), analysis.get('supplier_city'), analysis.get('supplier_zip_code'), analysis.get('supplier_country')]):
        addr = {
            'address': (analysis.get('supplier_street') or '')[:100],
            'city': (analysis.get('supplier_city') or '')[:100],
            'zip': (analysis.get('supplier_zip_code') or '')[:50],
            'country': (analysis.get('supplier_country') or '')[:100],
            'state': ''
        }
        update_data['billing_address'] = addr
        update_data['shipping_address'] = addr.copy()

    # notes
    if analysis.get('bank_name') or analysis.get('iban') or analysis.get('swift_bic'):
        parts = []
        if analysis.get('bank_name'):
            parts.append(f"Bank: {analysis['bank_name']}")
        if analysis.get('iban') or analysis.get('bank_account'):
            parts.append(f"Account: {analysis.get('iban') or analysis.get('bank_account')}")
        if analysis.get('swift_bic'):
            parts.append(f"SWIFT: {analysis['swift_bic']}")
        update_data['notes'] = ' | '.join(parts)[:100]

    if update_data:
        resp_other = await zoho_client._make_request('PUT', url, json=_trim_100(update_data))
        other_applied = bool(resp_other and (resp_other.get('code') == 0 or resp_other.get('contact')))

    # Verify VAT
    if doc_vat and not vat_applied:
        try:
            latest = await zoho_client.get_contact_details(org_id, contact_id) or {}
            values = set()
            for k in ['cf_tax_id', 'cf_vat_id']:
                if latest.get(k):
                    values.add(str(latest.get(k)))
            for cf in (latest.get('custom_fields') or []):
                v = (cf.get('value') or '').strip()
                if v:
                    values.add(v)
            vat_applied = doc_vat in values or any(v[2:] == doc_vat[2:] for v in values if len(v) > 2 and v[:2].isalpha())
        except Exception:
            pass

    return vat_applied, other_applied, doc_vat


