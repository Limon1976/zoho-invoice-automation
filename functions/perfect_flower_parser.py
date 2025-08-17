"""
Идеальный парсер цветочных документов - ТОЧНАЯ КОПИЯ из test_full_invoice_summary.py
"""

import pdfplumber
import re

def extract_perfect_flower_data(pdf_path: str):
    """
    Извлекает данные цветочного документа с идеальной точностью.
    Возвращает данные в формате для Zoho Bills API.
    """
    
    positions = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            
            for table in tables:
                # На первой странице пропускаем заголовок, на второй - нет
                start_row = 1 if page_num == 0 else 0
                
                for row in table[start_row:]:
                    if row and len(row) >= 7:
                        pos_cell = row[0].strip() if row[0] else ''
                        name_cell = row[1].strip() if row[1] else ''
                        qty_cell = row[3].strip() if row[3] else ''
                        price_brutto_cell = row[6].strip() if row[6] else ''
                        sum_netto_cell = row[7].strip() if row[7] else ''
                        vat_cell = row[8].strip() if row[8] else ''
                        vat_amount_cell = row[9].strip() if row[9] else ''
                        sum_brutto_cell = row[10].strip() if row[10] else ''
                        
                        if (pos_cell.isdigit() and 
                            1 <= int(pos_cell) <= 50 and
                            name_cell and len(name_cell) > 3):
                            
                            pos_num = int(pos_cell)
                            quantity = int(qty_cell) if qty_cell.isdigit() else None
                            
                            # Цена брутто за единицу
                            unit_price_brutto = None
                            if price_brutto_cell:
                                price_match = re.search(r'(\d+[,\.]\d+)', price_brutto_cell)
                                if price_match:
                                    unit_price_brutto = float(price_match.group(1).replace(',', '.'))
                            
                            # Сумма нетто
                            sum_netto = None
                            if sum_netto_cell:
                                sum_match = re.search(r'(\d+[,\.]\d+)', sum_netto_cell)
                                if sum_match:
                                    sum_netto = float(sum_match.group(1).replace(',', '.'))
                            
                            # VAT процент
                            vat_percent = 8  # По умолчанию
                            if vat_cell:
                                vat_match = re.search(r'(\d+)%', vat_cell)
                                if vat_match:
                                    vat_percent = int(vat_match.group(1))
                            
                            # Цена нетто за единицу (рассчитываем из sum_netto / quantity)
                            unit_price_netto = None
                            if sum_netto and quantity:
                                unit_price_netto = round(sum_netto / quantity, 2)
                            
                            # Если нет unit_price_netto, вычисляем из брутто
                            if not unit_price_netto and unit_price_brutto and vat_percent:
                                unit_price_netto = round(unit_price_brutto / (1 + vat_percent / 100), 2)
                            
                            if quantity and unit_price_netto:
                                positions.append({
                                    'position': pos_num,
                                    'name': name_cell,
                                    'quantity': quantity,
                                    'unit_price_netto': unit_price_netto,
                                    'unit_price_brutto': unit_price_brutto,
                                    'vat_percent': vat_percent,
                                    'sum_netto': sum_netto
                                })
    
    # Сортируем по позиции
    positions.sort(key=lambda x: x['position'])
    return positions

def convert_to_zoho_line_items(positions, inclusive_tax=True, org_id=None):
    """
    Конвертирует позиции в формат line_items для Zoho Bills API
    """
    line_items = []
    
    # Импортируем функцию поиска tax_id
    try:
        from functions.zoho_api import find_tax_by_percent
    except ImportError:
        find_tax_by_percent = None
    
    for pos in positions:
        # ПРАВИЛЬНАЯ ЛОГИКА: используем БРУТТО цену для inclusive tax документов
        if inclusive_tax and pos.get('unit_price_brutto'):
            rate = float(pos['unit_price_brutto'])  # Цена БРУТТО для inclusive
        else:
            rate = float(pos.get('unit_price_netto', 0))  # Цена НЕТТО для exclusive
            
        # Определяем VAT процент из данных
        vat_percent = pos.get('vat_percent', 8)  # По умолчанию 8%
        
        item = {
            "name": pos['name'][:200],
            "description": pos['name'][:2000], 
            "quantity": float(pos['quantity']),
            "rate": rate,
        }
        
        # Добавляем tax_id если можем определить
        if find_tax_by_percent and org_id and vat_percent > 0:
            tax_id = find_tax_by_percent(org_id, vat_percent)
            if tax_id:
                item["tax_id"] = tax_id
            else:
                item["tax_id"] = "-1" if not inclusive_tax else None
        
        line_items.append(item)
    
    return line_items

if __name__ == "__main__":
    # Быстрый тест
    pdf_path = 'processed_files/FV A_3538_2025_20250816_234721.pdf'
    
    print("🌸 ТЕСТ ИДЕАЛЬНОГО ПАРСЕРА")
    positions = extract_perfect_flower_data(pdf_path)
    print(f"Найдено позиций: {len(positions)}")
    
    line_items = convert_to_zoho_line_items(positions)
    print(f"Line items для Zoho: {len(line_items)}")
    
    print("\n=== ПЕРВЫЕ 3 ПОЗИЦИИ ===")
    for item in line_items[:3]:
        print(f"Name: {item['name']}")
        print(f"Quantity: {item['quantity']}")
        print(f"Rate: {item['rate']}")
        print()
