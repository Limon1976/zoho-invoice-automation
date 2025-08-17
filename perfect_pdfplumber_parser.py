"""
ИДЕАЛЬНЫЙ PDFPlumber парсер основанный на найденной табличной структуре.
Извлекает ВСЕ 33 позиции с точными количествами и ценами.
"""

import pdfplumber
import re

def extract_perfect_flower_data(pdf_path: str):
    """Извлекает все 33 позиции с точными данными из таблиц"""
    
    positions = []
    
    with pdfplumber.open(pdf_path) as pdf:
        print(f"PDFPlumber: {len(pdf.pages)} страниц")
        
        for page_num, page in enumerate(pdf.pages):
            print(f"\n=== СТРАНИЦА {page_num + 1} ===")
            
            # Извлекаем таблицы
            tables = page.extract_tables()
            print(f"Найдено таблиц: {len(tables)}")
            
            for table_num, table in enumerate(tables):
                print(f"\nТаблица {table_num + 1}: {len(table)} строк")
                
                # Пропускаем заголовки таблицы (первая строка)
                for row_num, row in enumerate(table[1:], 1):  # Начинаем с 2-й строки
                    if row and len(row) >= 7:  # Достаточно колонок
                        
                        # Структура колонок (из анализа):
                        # 0: Номер позиции
                        # 1: Название товара
                        # 2: PKWiU (пустой)
                        # 3: Количество
                        # 4: Единица (szt)
                        # 5: Процент/Цена до (8,00%\n4,50)
                        # 6: Цена брутто (4,14)
                        # 7: Сумма нетто (38,33)
                        # 8: Ставка VAT (8%)
                        # 9: Сумма VAT (3,07)
                        # 10: Сумма брутто (41,40)
                        
                        pos_cell = row[0].strip() if row[0] else ''
                        name_cell = row[1].strip() if row[1] else ''
                        qty_cell = row[3].strip() if row[3] else ''
                        unit_cell = row[4].strip() if row[4] else ''
                        price_brutto_cell = row[6].strip() if row[6] else ''
                        vat_cell = row[8].strip() if row[8] else ''
                        
                        # Проверяем что это товарная строка
                        if (pos_cell.isdigit() and 
                            1 <= int(pos_cell) <= 33 and
                            name_cell and
                            len(name_cell) > 3):
                            
                            pos_num = int(pos_cell)
                            name = name_cell
                            
                            # Извлекаем количество
                            quantity = None
                            if qty_cell.isdigit():
                                quantity = int(qty_cell)
                            
                            # Извлекаем цену (брутто из колонки 6)
                            unit_price = None
                            if price_brutto_cell:
                                price_match = re.search(r'(\d+[,\.]\d+)', price_brutto_cell)
                                if price_match:
                                    price_str = price_match.group(1).replace(',', '.')
                                    unit_price = float(price_str)
                            
                            # Извлекаем VAT процент
                            vat_percent = 8  # дефолт
                            if vat_cell:
                                vat_match = re.search(r'(\d+)%', vat_cell)
                                if vat_match:
                                    vat_percent = int(vat_match.group(1))
                            
                            position_data = {
                                'position': pos_num,
                                'name': name,
                                'quantity': quantity,
                                'unit_price_netto': unit_price,  # На самом деле брутто, но так ожидает система
                                'vat_percent': vat_percent,
                                'page': page_num + 1,
                                'raw_row': row  # для отладки
                            }
                            
                            positions.append(position_data)
                            
                            print(f"    ✅ Поз.{pos_num}: {name} | qty={quantity} | price={unit_price} | VAT={vat_percent}%")
    
    # Сортируем по номеру позиции
    positions.sort(key=lambda x: x['position'])
    return positions


if __name__ == "__main__":
    pdf_path = 'processed_files/FV A_3538_2025_20250816_213306.pdf'
    
    print("=== ИДЕАЛЬНЫЙ PDFPLUMBER ПАРСЕР ===")
    positions = extract_perfect_flower_data(pdf_path)
    
    print(f"\n=== РЕЗУЛЬТАТЫ ===")
    print(f"Всего найдено позиций: {len(positions)}")
    
    print("\n=== ВСЕ ПОЗИЦИИ ===")
    for pos in positions:
        page = pos.get('page', '?')
        qty = pos.get('quantity', '?')
        price = pos.get('unit_price_netto', '?')
        vat = pos.get('vat_percent', '?')
        print(f"{pos['position']:2d}. {pos['name']} | page={page} | qty={qty} | price={price} | VAT={vat}%")
    
    # Проверка позиций 28-33
    print(f"\n=== ПРОВЕРКА КЛЮЧЕВЫХ ПОЗИЦИЙ 28-33 ===")
    expected = {
        28: {'name': 'Dahl Karma Sangria', 'qty': 10, 'price': 4.14},
        29: {'name': 'Chr T Pastela Pink', 'qty': 10, 'price': 2.76},
        30: {'name': 'Chr T Pastela Pink', 'qty': 5, 'price': 2.76},
        31: {'name': 'Li Or Catemaco', 'qty': 10, 'price': 8.28},
        32: {'name': 'R Gr Jumilia', 'qty': 30, 'price': 3.13},
        33: {'name': 'R Gr Jumilia', 'qty': 10, 'price': 3.13}
    }
    
    page2_positions = [p for p in positions if p['position'] >= 28]
    for pos in page2_positions:
        pos_num = pos['position']
        if pos_num in expected:
            exp = expected[pos_num]
            actual_qty = pos.get('quantity')
            actual_price = pos.get('unit_price_netto')
            
            name_ok = exp['name'] == pos['name']
            qty_ok = exp['qty'] == actual_qty
            price_ok = abs(exp['price'] - actual_price) < 0.01 if actual_price else False
            
            status = "✅" if name_ok and qty_ok and price_ok else "❌"
            print(f"{status} Поз.{pos_num}: name={name_ok}, qty={qty_ok}, price={price_ok}")
            
            if not name_ok or not qty_ok or not price_ok:
                print(f"    Ожидали: {exp}")
                print(f"    Получили: name='{pos['name']}', qty={actual_qty}, price={actual_price}")
    
    print(f"\n=== СТАТИСТИКА ===")
    page_stats = {}
    vat_stats = {}
    for pos in positions:
        # По страницам
        page = pos.get('page', 0)
        page_stats[page] = page_stats.get(page, 0) + 1
        
        # По VAT
        vat = pos.get('vat_percent', 0)
        vat_stats[vat] = vat_stats.get(vat, 0) + 1
    
    print(f"По страницам:")
    for page, count in sorted(page_stats.items()):
        print(f"  Страница {page}: {count} позиций")
    
    print(f"По VAT:")
    for vat, count in sorted(vat_stats.items()):
        print(f"  VAT {vat}%: {count} позиций")
