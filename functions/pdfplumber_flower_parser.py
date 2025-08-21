"""
PDFPlumber Flower Invoice Parser
Идеальный парсер для цветочных инвойсов HIBISPOL с поддержкой многостраничных документов
"""

import pdfplumber
import re
import logging

logger = logging.getLogger(__name__)

def extract_flower_positions_pdfplumber(pdf_path):
    """
    Извлекает позиции цветов из PDF используя PDFPlumber для точного парсинга таблиц
    
    Args:
        pdf_path (str): Путь к PDF файлу
        
    Returns:
        list: Список позиций в формате:
        {
            'position': int,
            'name': str,
            'quantity': int,
            'unit_price_netto': float,
            'unit_price_brutto': float,
            'vat_percent': int,
            'total_netto': float,
            'total_vat': float,
            'total_brutto': float
        }
    """
    positions = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            logger.info(f"🌸 PDFPlumber: Обрабатываем {len(pdf.pages)} страниц")
            
            for page_num, page in enumerate(pdf.pages):
                logger.info(f"🌸 PDFPlumber: Страница {page_num + 1}")
                
                tables = page.extract_tables()
                logger.info(f"🌸 PDFPlumber: Найдено {len(tables)} таблиц на странице {page_num + 1}")
                
                for table_idx, table in enumerate(tables):
                    if not table:
                        continue
                        
                    logger.info(f"🌸 PDFPlumber: Таблица {table_idx + 1} содержит {len(table)} строк")
                    
                    # На первой странице пропускаем заголовок таблицы
                    start_row = 1 if page_num == 0 else 0
                    
                    for row_idx, row in enumerate(table[start_row:], start=start_row):
                        if not row or len(row) < 11:  # Минимум 11 колонок для полной таблицы
                            continue
                            
                        # Извлекаем данные из колонок
                        pos_cell = str(row[0]).strip() if row[0] else ''
                        name_cell = str(row[1]).strip() if row[1] else ''
                        unit_cell = str(row[2]).strip() if row[2] else ''  # szt
                        qty_cell = str(row[3]).strip() if row[3] else ''
                        price_netto_cell = str(row[4]).strip() if row[4] else ''
                        sum_netto_cell = str(row[5]).strip() if row[5] else ''
                        price_brutto_cell = str(row[6]).strip() if row[6] else ''
                        sum_netto_cell2 = str(row[7]).strip() if row[7] else ''  # Дублирует col 5
                        vat_cell = str(row[8]).strip() if row[8] else ''
                        vat_amount_cell = str(row[9]).strip() if row[9] else ''
                        sum_brutto_cell = str(row[10]).strip() if row[10] else ''
                        
                        # Проверяем, что это валидная строка позиции
                        if not (pos_cell.isdigit() and 1 <= int(pos_cell) <= 100):
                            continue
                            
                        if not name_cell or len(name_cell) < 3:
                            continue
                            
                        pos_num = int(pos_cell)
                        
                        # Извлекаем количество
                        quantity = None
                        if qty_cell.isdigit():
                            quantity = int(qty_cell)
                        
                        # Извлекаем цену нетто за единицу
                        unit_price_netto = None
                        if price_netto_cell:
                            price_match = re.search(r'(\d+[,.]?\d*)', price_netto_cell)
                            if price_match:
                                unit_price_netto = float(price_match.group(1).replace(',', '.'))
                        
                        # Извлекаем цену брутто за единицу
                        unit_price_brutto = None
                        if price_brutto_cell:
                            price_match = re.search(r'(\d+[,.]?\d*)', price_brutto_cell)
                            if price_match:
                                unit_price_brutto = float(price_match.group(1).replace(',', '.'))
                        
                        # Извлекаем сумму нетто
                        total_netto = None
                        sum_cell = sum_netto_cell2 if sum_netto_cell2 else sum_netto_cell
                        if sum_cell:
                            sum_match = re.search(r'(\d+[,.]?\d*)', sum_cell)
                            if sum_match:
                                total_netto = float(sum_match.group(1).replace(',', '.'))
                        
                        # Извлекаем VAT процент
                        vat_percent = 8  # По умолчанию
                        if vat_cell:
                            vat_match = re.search(r'(\d+)%', vat_cell)
                            if vat_match:
                                vat_percent = int(vat_match.group(1))
                        
                        # Извлекаем сумму VAT
                        total_vat = None
                        if vat_amount_cell:
                            vat_match = re.search(r'(\d+[,.]?\d*)', vat_amount_cell)
                            if vat_match:
                                total_vat = float(vat_match.group(1).replace(',', '.'))
                        
                        # Извлекаем общую сумму брутто
                        total_brutto = None
                        if sum_brutto_cell:
                            sum_match = re.search(r'(\d+[,.]?\d*)', sum_brutto_cell)
                            if sum_match:
                                total_brutto = float(sum_match.group(1).replace(',', '.'))
                        
                        # Вычисляем недостающие значения
                        if unit_price_netto is None and unit_price_brutto and vat_percent:
                            # Цена нетто = цена брутто / (1 + VAT/100)
                            unit_price_netto = unit_price_brutto / (1 + vat_percent / 100)
                        
                        if total_vat is None and total_netto and vat_percent:
                            # VAT = нетто * VAT%/100
                            total_vat = total_netto * vat_percent / 100
                        
                        if total_brutto is None and total_netto and total_vat:
                            # Брутто = нетто + VAT
                            total_brutto = total_netto + total_vat
                        
                        position_data = {
                            'position': pos_num,
                            'name': name_cell,
                            'quantity': quantity,
                            'unit_price_netto': round(unit_price_netto, 2) if unit_price_netto else None,
                            'unit_price_brutto': round(unit_price_brutto, 2) if unit_price_brutto else None,
                            'vat_percent': vat_percent,
                            'total_netto': round(total_netto, 2) if total_netto else None,
                            'total_vat': round(total_vat, 2) if total_vat else None,
                            'total_brutto': round(total_brutto, 2) if total_brutto else None
                        }
                        
                        positions.append(position_data)
                        
                        logger.info(f"🌸 PDFPlumber: Поз.{pos_num} - {name_cell[:30]} | {quantity}шт | VAT {vat_percent}%")
        
        # Сортируем по номеру позиции
        positions.sort(key=lambda x: x['position'])
        
        # Статистика
        total_positions = len(positions)
        vat_breakdown = {}
        for pos in positions:
            vat = pos['vat_percent']
            vat_breakdown[vat] = vat_breakdown.get(vat, 0) + 1
        
        logger.info(f"🌸 PDFPlumber: ИТОГО извлечено {total_positions} позиций")
        for vat, count in sorted(vat_breakdown.items()):
            logger.info(f"🌸 PDFPlumber: VAT {vat}% - {count} позиций")
            
        return positions
        
    except Exception as e:
        logger.error(f"❌ PDFPlumber: Ошибка парсинга: {e}")
        return []

def convert_to_zoho_format(positions):
    """
    Конвертирует позиции PDFPlumber в формат для Zoho Bills API
    
    Args:
        positions (list): Позиции из extract_flower_positions_pdfplumber
        
    Returns:
        list: Позиции в формате Zoho API
    """
    zoho_items = []
    
    for pos in positions:
        if not all([pos.get('name'), pos.get('quantity'), pos.get('unit_price_netto')]):
            logger.warning(f"🌸 PDFPlumber: Пропускаем позицию {pos.get('position')} - неполные данные")
            continue
            
        # Определяем включенность налога по VAT
        inclusive = pos['vat_percent'] > 0
        
        zoho_item = {
            'name': pos['name'],
            'description': pos['name'],
            'quantity': pos['quantity'],
            'rate': pos['unit_price_netto'],  # Используем цену нетто
            'tax_percentage': pos['vat_percent'],
            'tax_type': 'inclusive' if inclusive else 'exclusive'
        }
        
        zoho_items.append(zoho_item)
        
    logger.info(f"🌸 PDFPlumber: Конвертировано {len(zoho_items)} позиций для Zoho")
    return zoho_items


