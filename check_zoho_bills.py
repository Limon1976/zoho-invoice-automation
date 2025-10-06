#!/usr/bin/env python3
"""
Проверка созданных Bills в Zoho Books
"""

import os
import sys
import requests
import json
from datetime import datetime

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from functions.zoho_api import get_access_token

def check_recent_bills():
    """Проверяем недавно созданные Bills в Zoho Books"""
    
    print("🔍 ПРОВЕРКА СОЗДАННЫХ BILLS В ZOHO BOOKS")
    print("=" * 50)
    
    try:
        # Получаем токен
        access_token = get_access_token()
        if not access_token:
            print("❌ Не удалось получить access token")
            return
        
        # PARKENTERTAINMENT org_id
        org_id = "20082562863"
        
        # Получаем список Bills за последние дни
        url = f"https://www.zohoapis.eu/books/v3/bills?organization_id={org_id}&sort_column=date&sort_order=D&per_page=20"
        headers = {
            "Authorization": f"Zoho-oauthtoken {access_token}",
            "Content-Type": "application/json"
        }
        
        print(f"📤 Запрашиваем Bills из Zoho...")
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"❌ Ошибка API: {response.status_code}")
            print(f"Response: {response.text}")
            return
        
        data = response.json()
        bills = data.get('bills', [])
        
        print(f"📋 Найдено Bills: {len(bills)}")
        
        # Ищем Bills созданные сегодня
        today = datetime.now().strftime('%Y-%m-%d')
        today_bills = []
        
        for bill in bills:
            bill_date = bill.get('date', '')
            created_time = bill.get('created_time', '')
            if today in bill_date or today in created_time:
                today_bills.append(bill)
        
        print(f"📅 Bills созданные сегодня ({today}): {len(today_bills)}")
        
        if today_bills:
            print(f"\n📋 СЕГОДНЯШНИЕ BILLS:")
            for i, bill in enumerate(today_bills, 1):
                bill_number = bill.get('bill_number', 'Unknown')
                vendor_name = bill.get('vendor_name', 'Unknown')
                total = bill.get('total', 0)
                currency = bill.get('currency_code', 'PLN')
                bill_id = bill.get('bill_id', '')
                status = bill.get('status', 'Unknown')
                created_time = bill.get('created_time', '')
                
                print(f"\n{i}. Bill #{bill_number}")
                print(f"   🏪 Поставщик: {vendor_name}")
                print(f"   💰 Сумма: {total} {currency}")
                print(f"   📊 Статус: {status}")
                print(f"   🕐 Создан: {created_time}")
                print(f"   🔗 URL: https://books.zoho.eu/app/{org_id}#/bills/{bill_id}")
                
                # Проверяем конкретный Bill #000040289
                if bill_number == "000040289":
                    print(f"   ⭐ ЭТО BILL ИЗ НАШЕГО ТЕСТА!")
        
        # Ищем конкретный Bill #000040289
        target_bill = None
        for bill in bills:
            if bill.get('bill_number') == "000040289":
                target_bill = bill
                break
        
        if target_bill:
            print(f"\n⭐ НАЙДЕН ТЕСТОВЫЙ BILL #000040289:")
            print(f"   🏪 Поставщик: {target_bill.get('vendor_name')}")
            print(f"   💰 Сумма: {target_bill.get('total')} {target_bill.get('currency_code')}")
            print(f"   📅 Дата: {target_bill.get('date')}")
            print(f"   🆔 ID: {target_bill.get('bill_id')}")
            print(f"   📊 Статус: {target_bill.get('status')}")
            print(f"   🔗 Прямая ссылка: https://books.zoho.eu/app/{org_id}#/bills/{target_bill.get('bill_id')}")
        else:
            print(f"\n❌ Bill #000040289 не найден в последних 20 Bills")
        
        # Проверяем также Expenses
        print(f"\n" + "=" * 50)
        print(f"💰 ПРОВЕРКА EXPENSES:")
        
        expense_url = f"https://www.zohoapis.eu/books/v3/expenses?organization_id={org_id}&sort_column=date&sort_order=D&per_page=10"
        expense_response = requests.get(expense_url, headers=headers)
        
        if expense_response.status_code == 200:
            expense_data = expense_response.json()
            expenses = expense_data.get('expenses', [])
            
            print(f"💰 Найдено Expenses: {len(expenses)}")
            
            today_expenses = []
            for expense in expenses:
                expense_date = expense.get('date', '')
                created_time = expense.get('created_time', '')
                if today in expense_date or today in created_time:
                    today_expenses.append(expense)
            
            if today_expenses:
                print(f"\n💰 СЕГОДНЯШНИЕ EXPENSES:")
                for i, expense in enumerate(today_expenses, 1):
                    expense_number = expense.get('expense_number', 'Unknown')
                    vendor_name = expense.get('vendor_name', 'Unknown')
                    amount = expense.get('amount', 0)
                    currency = expense.get('currency_code', 'PLN')
                    expense_id = expense.get('expense_id', '')
                    
                    print(f"\n{i}. Expense #{expense_number}")
                    print(f"   🏪 Поставщик: {vendor_name}")
                    print(f"   💰 Сумма: {amount} {currency}")
                    print(f"   🔗 URL: https://books.zoho.eu/app/{org_id}#/expenses/{expense_id}")
            else:
                print(f"📅 Нет Expenses созданных сегодня")
        else:
            print(f"❌ Ошибка получения Expenses: {expense_response.status_code}")
        
    except Exception as e:
        print(f"❌ Ошибка проверки Zoho: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_recent_bills()
