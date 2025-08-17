from __future__ import annotations

from typing import Optional, Dict
import phonenumbers

COUNTRY_TO_ISO = {
    'poland': 'PL', 'polska': 'PL',
    'estonia': 'EE', 'eesti': 'EE',
    'germany': 'DE', 'deutschland': 'DE',
    'latvia': 'LV', 'lithuania': 'LT', 'netherlands': 'NL',
    'ireland': 'IE', 'france': 'FR', 'spain': 'ES', 'italy': 'IT',
    'portugal': 'PT', 'sweden': 'SE', 'denmark': 'DK',
    'united kingdom': 'GB', 'uk': 'GB'
}

COUNTRY_CALLING_CODES = {
    'PL': '48', 'EE': '372', 'LV': '371', 'LT': '370', 'DE': '49', 'GB': '44', 'IE': '353',
    'FR': '33', 'ES': '34', 'IT': '39', 'PT': '351', 'SE': '46', 'DK': '45', 'NL': '31'
}


def normalize_phone(phone_raw: Optional[str], supplier_country: Optional[str]) -> Dict[str, str]:
    phone = (phone_raw or '').strip()
    if not phone:
        return {}
    region = COUNTRY_TO_ISO.get((supplier_country or '').strip().lower())
    try:
        num = phonenumbers.parse(phone, region)
        if not phonenumbers.is_valid_number(num):
            return {}
        national = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.NATIONAL)
        e164 = phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
        country_iso = phonenumbers.region_code_for_number(num) or region
        code = COUNTRY_CALLING_CODES.get(country_iso)
        return {
            'phone': ''.join(ch for ch in national if ch.isdigit()),
            'phone_code': code or '',
            'phone_country_code': code or '',
            'e164': e164,
            'region_iso': country_iso or ''
        }
    except Exception:
        return {}


