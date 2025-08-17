"""
PDFMiner парсер для цветочных документов HIBISPOL.
Извлекает ВСЕ позиции со всех страниц с правильными количествами и ценами.
"""

import re
import logging
from typing import List, Dict, Any
from pdfminer.high_level import extract_text

logger = logging.getLogger(__name__)


def extract_flowers_with_pdfminer(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Извлекает все цветочные позиции из PDF используя PDFMiner.
    Находит все позиции со всех страниц с точными количествами и ценами.
    
    Returns:
        List[Dict] с полями: position, name, quantity, unit_price_netto, vat_percent
    """
    try:
        # Извлекаем весь текст через PDFMiner
        logger.info(f"📖 PDFMiner: извлекаем текст из {pdf_path}")
        full_text = extract_text(pdf_path)
        logger.info(f"📖 PDFMiner: извлечено {len(full_text)} символов")
        
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        positions = []
        
        # Находим все товарные позиции (номер и название на отдельных строках)
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Ищем строку только с номером позиции
            if line.isdigit() and 1 <= int(line) <= 50:
                pos_num = int(line)
                
                # Название товара должно быть в следующих 3 строках
                name = None
                for j in range(i + 1, min(i + 4, len(lines))):
                    candidate = lines[j].strip()
                    # Проверяем что это название товара (содержит буквы и достаточно длинное)
                    if (candidate and 
                        len(candidate) > 3 and 
                        re.search(r'[a-zA-Z]', candidate) and
                        not candidate.isdigit() and
                        not re.match(r'^\d+[.,]\d+$', candidate) and
                        'szt' not in candidate.lower() and
                        '%' not in candidate):
                        name = candidate
                        break
                
                if name:
                    # Ищем количество и цену в окрестности (±15 строк)
                    quantity = None
                    unit_price = None
                    vat_percent = 8  # дефолт
                    
                    search_start = max(0, i - 5)
                    search_end = min(len(lines), i + 20)
                    
                    for j in range(search_start, search_end):
                        search_line = lines[j].strip()
                        
                        # Ищем количество (число + szt)
                        if quantity is None and 'szt' in search_line:
                            # Количество может быть в этой же строке или соседних
                            qty_match = re.search(r'(\d+)\s*szt', search_line)
                            if qty_match:
                                quantity = int(qty_match.group(1))
                            else:
                                # Проверяем соседние строки
                                for k in [j-2, j-1, j+1, j+2]:
                                    if 0 <= k < len(lines) and lines[k].strip().isdigit():
                                        candidate_qty = int(lines[k].strip())
                                        if 1 <= candidate_qty <= 200:  # разумный диапазон
                                            quantity = candidate_qty
                                            break
                        
                        # Ищем цену (формат X,XX)
                        if unit_price is None:
                            price_match = re.search(r'(\d{1,3}[,\.]\d{2})', search_line)
                            if price_match:
                                price_str = price_match.group(1).replace(',', '.')
                                price_val = float(price_str)
                                # Берем разумную цену за единицу
                                if 0.5 <= price_val <= 100:
                                    unit_price = price_val
                        
                        # Ищем VAT процент
                        vat_match = re.search(r'(\d+)%', search_line)
                        if vat_match:
                            vat_percent = int(vat_match.group(1))
                    
                    # Если нашли основные данные, добавляем позицию
                    if quantity and unit_price:
                        positions.append({
                            'position': pos_num,
                            'name': name,
                            'quantity': quantity,
                            'unit_price_netto': unit_price,
                            'vat_percent': vat_percent
                        })
                        logger.info(f"✅ Поз.{pos_num}: {name} | qty={quantity} | price={unit_price} | VAT={vat_percent}%")
                    else:
                        logger.warning(f"❌ Поз.{pos_num}: {name} - не найдены qty={quantity} или price={unit_price}")
            
            i += 1
        
        # Сортируем по номеру позиции
        positions.sort(key=lambda x: x['position'])
        
        logger.info(f"📋 PDFMiner: найдено {len(positions)} позиций")
        return positions
        
    except Exception as e:
        logger.error(f"❌ Ошибка PDFMiner парсинга: {e}")
        return []


def is_suitable_for_pdfminer(pdf_path: str) -> bool:
    """
    Проверяет подходит ли документ для PDFMiner парсинга.
    """
    try:
        text = extract_text(pdf_path)
        # Проверяем что есть текстовый слой и товарные позиции
        has_positions = bool(re.search(r'\d+\s+[A-Za-z]', text))
        has_quantities = 'szt' in text.lower()
        
        logger.info(f"📋 PDFMiner проверка: позиции={has_positions}, количества={has_quantities}")
        return has_positions and has_quantities
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки PDFMiner: {e}")
        return False
