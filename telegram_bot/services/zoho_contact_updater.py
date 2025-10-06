from __future__ import annotations

from typing import Dict, Any, Tuple, Optional

from .vat_normalizer import normalize_vat
from .phone_normalizer import normalize_phone


def _trim_100(value: Any) -> Any:
    if isinstance(value, str):
        return value[:100]
    if isinstance(value, list):
        return [_trim_100(v) for v in value]
    if isinstance(value, dict):
        return {k: _trim_100(v) for k, v in value.items()}
    return value


async def _resolve_vat_cf_id(zoho_client, org_id: str, contact_id: str, vat_api: str) -> Optional[str]:
    try:
        details = await zoho_client.get_contact_details(org_id, contact_id) or {}
        for cf in (details.get('custom_fields') or []):
            if (cf.get('api_name') or '') == vat_api and cf.get('customfield_id'):
                return cf['customfield_id']
    except Exception:
        return None
    return None


async def _find_vat_index(zoho_client, org_id: str) -> Optional[int]:
    """Read settings/customfields and try to find VAT/TAX ID index for Contacts module."""
    try:
        meta = await zoho_client.get_contact_custom_fields(org_id) or {}
        fields = meta.get("customfields") or []
        for f in fields:
            try:
                if f.get("module") != "contacts":
                    continue
                label = (f.get("label") or "").strip().lower()
                api = (f.get("api_name") or "").strip().lower()
                if label in {"tax id", "vat", "vat id", "vat number"} or api in {"cf_tax_id", "cf_vat_id"}:
                    return int(f.get("index")) if f.get("index") is not None else None
            except Exception:
                continue
    except Exception:
        return None
    return None


async def update_contact(zoho_client, org_id: str, contact_id: str, analysis: Dict[str, Any]) -> Tuple[bool, bool, Optional[str]]:
    """Minimal, deterministic updater. Returns (vat_applied, other_applied, doc_vat)."""
    url = f"https://www.zohoapis.eu/books/v3/contacts/{contact_id}?organization_id={org_id}"

    # 1) VAT
    doc_vat = normalize_vat(analysis.get('supplier_vat'), analysis.get('supplier_country'), analysis.get('extracted_text'))
    vat_applied = False
    if doc_vat:
        vat_api = 'cf_tax_id' if org_id == '20082562863' else 'cf_vat_id'
        cf_id = await _resolve_vat_cf_id(zoho_client, org_id, contact_id, vat_api)
        # Primary attempt: by customfield_id or api_name
        vat_payload = {"custom_fields": [{"customfield_id": cf_id, "value": doc_vat}]} if cf_id else {"custom_fields": [{"api_name": vat_api, "value": doc_vat}]}
        try:
            print(f"VAT PUT primary payload={vat_payload}")
        except Exception:
            pass
        resp_vat = await zoho_client._make_request('PUT', url, json=_trim_100(vat_payload))
        vat_applied = bool(resp_vat and (resp_vat.get('code') == 0 or resp_vat.get('contact')))
        # Fallback: by index from settings if primary failed
        if not vat_applied:
            index = await _find_vat_index(zoho_client, org_id)
            if index is not None:
                vat_payload_idx = {"custom_fields": [{"index": index, "value": doc_vat}]}
                try:
                    print(f"VAT PUT fallback(index) payload={vat_payload_idx}")
                except Exception:
                    pass
                resp_idx = await zoho_client._make_request('PUT', url, json=_trim_100(vat_payload_idx))
                vat_applied = bool(resp_idx and (resp_idx.get('code') == 0 or resp_idx.get('contact')))

    # 2) Other fields
    update_data: Dict[str, Any] = {}
    
    # Email обновление
    if analysis.get('supplier_email'):
        email = analysis.get('supplier_email').strip()
        if email and '@' in email:
            update_data['email'] = email[:100]
    
    # Phone обновление
    phone_info = normalize_phone(analysis.get('supplier_phone'), analysis.get('supplier_country'))
    if phone_info:
        update_data['phone'] = phone_info.get('phone')
        if phone_info.get('phone_code'):
            update_data['phone_code'] = phone_info['phone_code']
            update_data['phone_country_code'] = phone_info['phone_code']

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

    if analysis.get('bank_name') or analysis.get('iban') or analysis.get('swift_bic'):
        parts = []
        if analysis.get('bank_name'):
            parts.append(f"Bank: {analysis['bank_name']}")
        if analysis.get('iban') or analysis.get('bank_account'):
            parts.append(f"Account: {analysis.get('iban') or analysis.get('bank_account')}")
        if analysis.get('swift_bic'):
            parts.append(f"SWIFT: {analysis['swift_bic']}")
        update_data['notes'] = ' | '.join(parts)[:100]

    other_applied = False
    if update_data:
        resp_other = await zoho_client._make_request('PUT', url, json=_trim_100(update_data))
        other_applied = bool(resp_other and (resp_other.get('code') == 0 or resp_other.get('contact')))

    # 3) Verify VAT if not applied
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


