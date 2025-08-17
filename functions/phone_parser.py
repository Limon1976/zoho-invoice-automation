"""
Модуль для парсинга и форматирования телефонных номеров
Автоматическое определение кода страны и правильное форматирование для Zoho Books API
"""

import logging
from typing import Optional, Dict, Any
import re

try:
    import phonenumbers
    from phonenumbers import geocoder, carrier
    from phonenumbers.phonenumberutil import NumberParseException
    PHONENUMBERS_AVAILABLE = True
except ImportError:
    PHONENUMBERS_AVAILABLE = False
    logging.warning("📞 Библиотека phonenumbers не установлена. Установите: pip install phonenumbers")

logger = logging.getLogger(__name__)

def parse_phone_number(phone_str: str, default_region: Optional[str] = None) -> Dict[str, Any]:
    """
    Парсит телефонный номер и возвращает структурированные данные
    
    Args:
        phone_str: Телефонный номер в любом формате (например: "+4982148068100", "020 8366 1177", "+371 29 510 500")
    
    Returns:
        Dict с полями:
        - original: исходный номер
        - is_valid: валиден ли номер
        - country_code: код страны (например: 49, 44, 371)
        - national_number: национальный номер без кода страны
        - formatted_international: международный формат (+49 821 48068100)
        - formatted_national: национальный формат (0821 48068100)
        - formatted_e164: E.164 формат (+4982148068100) 
        - country_name: название страны (если доступно)
        - carrier_name: название оператора (если доступно)
        - clean_number: очищенный номер без пробелов
        - zoho_format: оптимальный формат для Zoho API
    """
    
    if not phone_str:
        return _empty_phone_result(phone_str)
    
    # Очищаем номер от лишних символов, но сохраняем + в начале
    clean_phone = re.sub(r'[^\d+]', '', phone_str.strip())
    
    # Если нет библиотеки phonenumbers, возвращаем базовую очистку
    if not PHONENUMBERS_AVAILABLE:
        return _fallback_phone_parsing(phone_str, clean_phone)
    
    try:
        # Пытаемся парсить номер
        # Если номер начинается с +, то region не нужен. Иначе используем default_region (ISO2), если передан
        parsed_number = phonenumbers.parse(phone_str, None if phone_str.strip().startswith('+') else (default_region or None))
        
        # Проверяем валидность
        is_valid = phonenumbers.is_valid_number(parsed_number)
        is_possible = phonenumbers.is_possible_number(parsed_number)
        
        if not is_possible:
            logger.warning(f"📞 Номер не возможен: {phone_str}")
            return _fallback_phone_parsing(phone_str, clean_phone)
        
        if not is_valid:
            logger.warning(f"📞 Номер не валиден: {phone_str}")
        
        # Извлекаем данные
        country_code = parsed_number.country_code
        national_number = parsed_number.national_number
        
        # Форматируем в разных форматах
        formatted_international = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
        formatted_national = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.NATIONAL)
        formatted_e164 = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
        
        # Получаем дополнительную информацию
        country_name = _get_country_name(parsed_number)
        carrier_name = _get_carrier_name(parsed_number)
        
        # Определяем оптимальный формат для Zoho
        zoho_format = formatted_e164  # По умолчанию E.164
        
        result = {
            'original': phone_str,
            'is_valid': is_valid,
            'is_possible': is_possible,
            'country_code': country_code,
            'national_number': str(national_number),
            'formatted_international': formatted_international,
            'formatted_national': formatted_national,
            'formatted_e164': formatted_e164,
            'country_name': country_name,
            'carrier_name': carrier_name,
            'clean_number': clean_phone,
            'zoho_format': zoho_format
        }
        
        logger.info(f"📞 Успешно распарсен номер: {phone_str} -> {zoho_format} (страна: {country_name})")
        return result
        
    except NumberParseException as e:
        logger.warning(f"📞 Ошибка парсинга номера {phone_str}: {e}")
        return _fallback_phone_parsing(phone_str, clean_phone)
    except Exception as e:
        logger.error(f"📞 Неожиданная ошибка при парсинге {phone_str}: {e}")
        return _fallback_phone_parsing(phone_str, clean_phone)

def _get_country_name(parsed_number) -> Optional[str]:
    """Получает название страны для номера"""
    try:
        return geocoder.description_for_number(parsed_number, "en")
    except:
        return None

def _get_carrier_name(parsed_number) -> Optional[str]:
    """Получает название оператора для номера"""
    try:
        return carrier.name_for_number(parsed_number, "en")
    except:
        return None

def _empty_phone_result(original: str) -> Dict[str, Any]:
    """Возвращает пустой результат для пустого номера"""
    return {
        'original': original,
        'is_valid': False,
        'is_possible': False,
        'country_code': None,
        'national_number': '',
        'formatted_international': '',
        'formatted_national': '',
        'formatted_e164': '',
        'country_name': None,
        'carrier_name': None,
        'clean_number': '',
        'zoho_format': ''
    }

def _fallback_phone_parsing(original: str, clean_number: str) -> Dict[str, Any]:
    """Fallback парсинг когда phonenumbers недоступна или не может распарсить"""
    
    # Пытаемся хотя бы извлечь код страны из номера с +
    country_code = None
    national_number = clean_number
    
    if clean_number.startswith('+'):
        # Пытаемся извлечь код страны
        number_part = clean_number[1:]  # убираем +
        
        # Общие коды стран (1-3 цифры)
        for code_length in [3, 2, 1]:
            if len(number_part) > code_length:
                potential_code = number_part[:code_length]
                if _is_known_country_code(potential_code):
                    country_code = int(potential_code)
                    national_number = number_part[code_length:]
                    break
    
    return {
        'original': original,
        'is_valid': False,  # Не можем проверить без библиотеки
        'is_possible': bool(clean_number and len(clean_number) >= 7),
        'country_code': country_code,
        'national_number': national_number,
        'formatted_international': clean_number if clean_number.startswith('+') else f'+{clean_number}',
        'formatted_national': national_number,
        'formatted_e164': clean_number if clean_number.startswith('+') else f'+{clean_number}',
        'country_name': _get_country_name_by_code(country_code) if country_code else None,
        'carrier_name': None,
        'clean_number': clean_number,
        'zoho_format': clean_number if clean_number.startswith('+') else f'+{clean_number}' if clean_number else ''
    }

def _is_known_country_code(code: str) -> bool:
    """Проверяет является ли код известным кодом страны"""
    known_codes = {
        # Самые распространенные коды
        '1', '7', '20', '27', '30', '31', '32', '33', '34', '36', '39', '40', '41', '43', '44', '45', '46', '47', '48', '49',
        '51', '52', '53', '54', '55', '56', '57', '58', '60', '61', '62', '63', '64', '65', '66', '81', '82', '84', '86', '90',
        '91', '92', '93', '94', '95', '98', '212', '213', '216', '218', '220', '221', '222', '223', '224', '225', '226', '227',
        '228', '229', '230', '231', '232', '233', '234', '235', '236', '237', '238', '239', '240', '241', '242', '243', '244',
        '245', '246', '247', '248', '249', '250', '251', '252', '253', '254', '255', '256', '257', '258', '260', '261', '262',
        '263', '264', '265', '266', '267', '268', '269', '290', '291', '297', '298', '299', '350', '351', '352', '353', '354',
        '355', '356', '357', '358', '359', '370', '371', '372', '373', '374', '375', '376', '377', '378', '380', '381', '382',
        '383', '385', '386', '387', '389', '420', '421', '423', '500', '501', '502', '503', '504', '505', '506', '507', '508',
        '509', '590', '591', '592', '593', '594', '595', '596', '597', '598', '599', '670', '672', '673', '674', '675', '676',
        '677', '678', '679', '680', '681', '682', '683', '684', '685', '686', '687', '688', '689', '690', '691', '692', '850',
        '852', '853', '855', '856', '880', '886', '960', '961', '962', '963', '964', '965', '966', '967', '968', '970', '971',
        '972', '973', '974', '975', '976', '977', '992', '993', '994', '995', '996', '998'
    }
    return code in known_codes

def _get_country_name_by_code(country_code: int) -> Optional[str]:
    """Возвращает название страны по коду (базовое сопоставление)"""
    country_names = {
        1: "USA/Canada",
        7: "Russia/Kazakhstan", 
        49: "Germany",
        44: "United Kingdom",
        33: "France",
        39: "Italy",
        34: "Spain",
        48: "Poland",
        371: "Latvia",
        372: "Estonia",
        370: "Lithuania",
        46: "Sweden",
        47: "Norway",
        45: "Denmark",
        358: "Finland",
        31: "Netherlands",
        32: "Belgium",
        41: "Switzerland",
        43: "Austria",
        420: "Czech Republic",
        421: "Slovakia",
        36: "Hungary",
        40: "Romania",
        359: "Bulgaria",
        385: "Croatia",
        386: "Slovenia",
        381: "Serbia",
        382: "Montenegro",
        389: "North Macedonia",
        30: "Greece",
        90: "Turkey",
        380: "Ukraine",
        375: "Belarus",
        373: "Moldova"
    }
    return country_names.get(country_code)

def format_phone_for_zoho(phone_str: str) -> str:
    """
    Быстрая функция для форматирования телефона для Zoho API
    
    Args:
        phone_str: Исходный телефонный номер
    
    Returns:
        Отформатированный номер для Zoho или исходный номер если не удалось распарсить
    """
    if not phone_str:
        return ""
    
    parsed = parse_phone_number(phone_str)
    return parsed.get('zoho_format', phone_str)

# Экспорт основных функций
__all__ = ['parse_phone_number', 'format_phone_for_zoho']