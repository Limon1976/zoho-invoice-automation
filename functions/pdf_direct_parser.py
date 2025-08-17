#!/usr/bin/env python3
"""
Прямой парсер PDF таблиц без OCR
Интеграция для telegram bot
"""

import fitz  # PyMuPDF
import re
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

def parse_vat_table_from_pdf(text: str) -> Dict[float, int]:
    """
    Парсит таблицу VAT из текста документа:
    Zestawienie sprzedaży w/g stawek podatku:
    Netto Stawka Kwota VAT
    44,88 23%
    """
    vat_mapping = {}
    try:
        lines = text.split('\n')
        
        # Ищем таблицу VAT
        vat_table_start = -1
        for i, line in enumerate(lines):
            if 'zestawienie' in line.lower() and 'stawek' in line.lower():
                vat_table_start = i
                break
        
        if vat_table_start != -1:
            # Парсим следующие 10 строк после заголовка
            for i in range(vat_table_start + 1, min(vat_table_start + 10, len(lines))):
                line = lines[i].strip()
                # Ищем строки типа "44,88 23%" или "2894,54 8%"
                import re
                match = re.search(r'(\d+[,\.]\d+)\s+(\d+)%', line)
                if match:
                    amount = float(match.group(1).replace(',', '.'))
                    vat_rate = int(match.group(2))
                    vat_mapping[amount] = vat_rate
                    logger.info(f"📊 VAT mapping: {amount} PLN → {vat_rate}%")
    
    except Exception as e:
        logger.error(f"Ошибка парсинга VAT таблицы: {e}")
    
    return vat_mapping

def extract_flower_positions_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """
    ВОССТАНОВЛЕННЫЙ РАБОЧИЙ АЛГОРИТМ ИЗ perfect_pdf_parser.py
    """
    
    try:
        doc = fitz.open(pdf_path)
        positions = []
        
        table_found = False
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            logger.info(f"📄 Обрабатываем страницу {page_num + 1}, строк: {len(lines)}")
            
            # Парсим таблицу VAT из документа
            vat_mapping = parse_vat_table_from_pdf(text)
            
            # Ищем начало таблицы только на первой странице
            table_start = -1
            if page_num == 0:
                for i, line in enumerate(lines):
                    if 'Lp.' in line and 'Nazwa towaru' in line:
                        table_start = i
                        table_found = True
                        logger.info(f"📋 Найден заголовок таблицы на строке {i+1}")
                        break
                
                if table_start == -1:
                    logger.info("❌ Заголовок таблицы не найден на первой странице")
                    continue
            else:
                # На последующих страницах продолжаем парсинг, если таблица уже найдена
                if not table_found:
                    logger.info("❌ Таблица не была найдена на первой странице, пропускаем")
                    continue
                logger.info("✅ Продолжаем парсинг на второй странице")
                table_start = 0  # Начинаем с начала страницы
                
            # Парсим данные после заголовка
            i = table_start + 1
            while i < len(lines):
                line = lines[i]
                
                # Проверяем, не конец ли таблицы
                if any(keyword in line for keyword in ['RAZEM:', 'Razem do zapłaty', 'Słownie']):
                    break
                
                # Ищем название товара (содержит буквы, не является числом, единицей или заголовком)
                excluded_headers = ['szt', 'PKWiU / CN', 'Kwota', 'VAT', 'Wartość', 'brutto', 'netto', 'Stawka', 'Cena', 'Rabat%', 'przed', 'J.m.', 'Ilość', 'Cena przed']
                if (re.search(r'[A-Za-z]', line) and 
                    line not in excluded_headers and 
                    not re.match(r'^\d+[,%]\d*$', line) and
                    not re.match(r'^\d+%$', line)):
                    
                    # Это может быть название товара
                    name = line
                    
                    # Ищем данные для этой позиции в следующих строках
                    j = i + 1
                    
                    # Собираем данные в следующих 10 строках
                    collected_data = []
                    while j < min(i + 10, len(lines)):
                        collected_data.append(lines[j])
                        j += 1
                    
                    # Анализируем собранные данные по правильной структуре
                    position_num = None
                    quantity = None
                    price = None
                    
                    # Ожидаемая структура: номер позиции, количество, "szt", цена
                    for idx, data_line in enumerate(collected_data):
                        # Ищем номер позиции (первое число)
                        if position_num is None and re.match(r'^\d+$', data_line):
                            pos_num = int(data_line)
                            if 1 <= pos_num <= 27:
                                position_num = pos_num
                                
                                # Количество должно быть в следующей строке
                                if idx + 1 < len(collected_data):
                                    next_line = collected_data[idx + 1]
                                    if re.match(r'^\d+$', next_line):
                                        qty = int(next_line)
                                        if 1 <= qty <= 100:
                                            quantity = qty
                                
                                # Цена должна быть после "szt" (обычно через 1-2 строки)
                                for price_idx in range(idx + 2, min(idx + 5, len(collected_data))):
                                    price_line = collected_data[price_idx]
                                    if re.match(r'^\d+,\d+$', price_line):
                                        price_val = float(price_line.replace(',', '.'))
                                        if 0.5 <= price_val <= 100:
                                            price = price_val
                                            break
                                
                                # Ищем VAT в следующих строках после цены
                                vat_rate = 8  # дефолт
                                for vat_idx in range(idx + 3, min(idx + 8, len(collected_data))):
                                    vat_line = collected_data[vat_idx]
                                    if re.match(r'^\d+%$', vat_line):
                                        vat_rate = int(vat_line.replace('%', ''))
                                        break
                                
                                break
                    
                    # Если нашли все необходимые данные
                    if position_num and quantity and price:
                        # Используем VAT найденный в парсинге структуры документа
                        tax_rate = vat_rate  # Уже найден выше
                        
                        logger.info(f"📊 VAT для '{name}': {tax_rate}% (найден в структуре документа)")
                        
                        positions.append({
                            'position': position_num,
                            'name': name,
                            'quantity': quantity,
                            'unit_price_netto': price,
                            'vat_percent': tax_rate
                        })
                    
                    # Пропускаем обработанные строки
                    i = j
                else:
                    i += 1
        
        doc.close()
        
        # Сортируем по номеру позиции
        positions.sort(key=lambda x: x.get('position', 999))
        
        logger.info(f"✅ Извлечено {len(positions)} позиций из PDF")
        return positions
        
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга PDF: {e}")
        return []

def format_for_telegram_bot(pdf_positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Форматирует результат PDF парсера для совместимости с telegram bot
    
    Args:
        pdf_positions: Результат от extract_flower_positions_from_pdf
        
    Returns:
        Список в формате, совместимом с другими парсерами
    """
    
    formatted_lines = []
    for item in pdf_positions:
        formatted_lines.append({
            'name': item['name'],
            'quantity': item['quantity'],
            'price_net': item['unit_price_netto'],
            'tax_percent': item['vat_percent']
        })
    
    return formatted_lines

def is_suitable_for_pdf_parsing(file_path: str) -> bool:
    """
    Определяет, подходит ли документ для PDF парсинга
    
    Args:
        file_path: Путь к файлу
        
    Returns:
        True если документ подходит для PDF парсинга
    """
    
    try:
        if not file_path.lower().endswith('.pdf'):
            return False
            
        doc = fitz.open(file_path)
        
        # Проверяем есть ли текстовый слой
        has_text = False
        has_table_structure = False
        
        for page_num in range(min(2, len(doc))):  # Проверяем первые 2 страницы
            page = doc.load_page(page_num)
            text = page.get_text()
            
            if len(text.strip()) > 100:  # Есть достаточно текста
                has_text = True
                
                # Ищем признаки табличной структуры
                if any(keyword in text for keyword in [
                    'Lp.', 'Nazwa', 'Ilość', 'szt', 'Cena', 'Wartość', 'VAT'
                ]):
                    has_table_structure = True
                    break
        
        doc.close()
        
        result = has_text and has_table_structure
        logger.info(f"📋 PDF парсинг {'ПОДХОДИТ' if result else 'НЕ ПОДХОДИТ'} для {file_path}")
        logger.info(f"   Текстовый слой: {'✅' if has_text else '❌'}")
        logger.info(f"   Табличная структура: {'✅' if has_table_structure else '❌'}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки PDF: {e}")
        return False
