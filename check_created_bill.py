#!/usr/bin/env python3
"""
Проверяем созданный Bill #000040289 в Zoho Books
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from functions.zoho_api import get_access_token
import requests

def check_bill_000040289():
    """Проверяем Bill #000040289 в PARKENTERTAINMENT"""
    
    print("🔍 ПРОВЕРКА BILL #000040289 В ZOHO BOOKS")
    print("=" * 50)
    
    try:
        org_id = "20082562863"  # PARKENTERTAINMENT
        access_token = get_access_token()
        
        if not access_token:
            print("❌ Не удалось получить access token")
            return
        
        # Проверяем Bills
        bills_url = f"https://www.zohoapis.eu/books/v3/bills?organization_id={org_id}"
        expenses_url = f"https://www.zohoapis.eu/books/v3/expenses?organization_id={org_id}"
        headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
        
        # Проверяем Bills
        print("📋 ПРОВЕРЯЕМ BILLS:")
        bills_response = requests.get(bills_url, headers=headers)
        
        if bills_response.status_code == 200:
            bills_data = bills_response.json()
            bills = bills_data.get('bills', [])
            
            print(f"  📋 Найдено Bills: {len(bills)}")
            
            # Ищем Bill #000040289
            found_bill = None
            for bill in bills:
                if bill.get('bill_number') == '000040289':
                    found_bill = bill
                    break
            
            if found_bill:
                print(f"  ✅ BILL #000040289 НАЙДЕН!")
                print(f"    📋 ID: {found_bill.get('bill_id')}")
                print(f"    🏪 Поставщик: {found_bill.get('vendor_name')}")
                print(f"    💰 Сумма: {found_bill.get('total')} {found_bill.get('currency_code')}")
                print(f"    📅 Дата: {found_bill.get('date')}")
                print(f"    🔗 URL: https://books.zoho.eu/app/{org_id}#/bills/{found_bill.get('bill_id')}")
            else:
                print(f"  ❌ BILL #000040289 НЕ НАЙДЕН в Bills!")
        
        # Проверяем Expenses
        print(f"\n💰 ПРОВЕРЯЕМ EXPENSES:")
        expenses_response = requests.get(expenses_url, headers=headers)
        
        if expenses_response.status_code == 200:
            expenses_data = expenses_response.json()
            expenses = expenses_data.get('expenses', [])
            
            print(f"  💰 Найдено Expenses: {len(expenses)}")
            
            # Ищем Expense с reference #000040289 или от поставщика Rožany Zakątek
            found_expense = None
            rozany_expenses = []
            
            for expense in expenses:
                ref_num = expense.get('reference_number', '')
                vendor_name = expense.get('vendor_name', '')
                
                if ref_num == '000040289':
                    found_expense = expense
                    break
                elif 'rozany' in vendor_name.lower() or 'rožany' in vendor_name.lower():
                    rozany_expenses.append(expense)
            
            if found_expense:
                print(f"  ✅ EXPENSE с reference #000040289 НАЙДЕН!")
                print(f"    💰 ID: {found_expense.get('expense_id')}")
                print(f"    🏪 Поставщик: {found_expense.get('vendor_name')}")
                print(f"    💰 Сумма: {found_expense.get('total')} {found_expense.get('currency_code')}")
                print(f"    📅 Дата: {found_expense.get('date')}")
                print(f"    🔗 URL: https://books.zoho.eu/app/{org_id}#/expenses/{found_expense.get('expense_id')}")
            elif rozany_expenses:
                print(f"  ✅ Найдено {len(rozany_expenses)} Expenses от Rožany Zakątek:")
                for exp in rozany_expenses:
                    print(f"    - #{exp.get('expense_number')} - {exp.get('total')} {exp.get('currency_code')} - {exp.get('date')}")
            else:
                print(f"  ❌ EXPENSE #000040289 НЕ НАЙДЕН!")
                
                # Показываем последние 3 Expenses
                print(f"\n💰 ПОСЛЕДНИЕ 3 EXPENSES:")
                for expense in expenses[:3]:
                    print(f"    - #{expense.get('expense_number')} - {expense.get('vendor_name')} - {expense.get('total')} {expense.get('currency_code')}")
        else:
            print(f"  ❌ Ошибка API Expenses: {expenses_response.status_code}")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    check_bill_000040289()
