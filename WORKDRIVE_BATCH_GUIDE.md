# 🚀 WorkDrive Batch Processor - Руководство по использованию

## 📋 **ЧТО РЕАЛИЗОВАНО**

✅ **Полная интеграция WorkDrive → Zoho Books** с автоматической обработкой инвойсов  
✅ **Ежедневный batch processor** для обработки файлов в 23:59:59 (Warsaw time)  
✅ **LLM анализ документов** через существующий pipeline (agent_invoice_parser)  
✅ **Автоматическое создание поставщиков** если их нет в системе  
✅ **Telegram уведомления** с отчётами и ссылками на созданные Bills  
✅ **Дедупликация** - не обрабатывает уже обработанные файлы  
✅ **Обработка ошибок** с детальными логами и fallback'ами  

## 🗂️ **ФАЙЛЫ СИСТЕМЫ**

### **Основные модули:**
- `functions/workdrive_batch_processor.py` - главный batch processor
- `functions/zoho_workdrive.py` - API интеграция с WorkDrive  
- `functions/workdrive_scheduler.py` - планировщик ежедневных запусков

### **Конфигурация:**
- `.env` - токены WorkDrive и Telegram
- `data/workdrive_processed.json` - лог обработанных файлов
- `data/workdrive_batch/` - временная папка для скачанных файлов

## 🛠️ **НАСТРОЙКА**

### **1. Переменные окружения (.env)**
```bash
# WorkDrive OAuth токены
WORKDRIVE_CLIENT_ID=1000.72DNFIBNJY0W58PSBR8T1L2RXT83VN
WORKDRIVE_CLIENT_SECRET=d2fd3f3b8f034ca73423e07d40e5dc1f985bf3da2b
WORKDRIVE_REFRESH_TOKEN=1000.eb2d0d0e1c0fdef910b1a0ffd1f6d521.d427c27c5d259b1113a4e28ec9256480

# Telegram уведомления  
TELEGRAM_BOT_TOKEN=ваш_telegram_bot_token
ADMIN_ID=ваш_telegram_user_id
```

### **2. Папка в WorkDrive**
- **August папка**: `1zqms56fb76bbe95e469bacc06a33e010fb84`
- Система автоматически обрабатывает PDF файлы из этой папки
- Поддерживается фильтрация по дате создания (Warsaw timezone)

## 🚀 **ЗАПУСК**

### **Ручной тест (файлы за 19 августа):**
```bash
source venv/bin/activate
python functions/workdrive_batch_processor.py --test
```

### **Обработка конкретной даты:**
```bash
source venv/bin/activate  
python functions/workdrive_batch_processor.py --date 2025-08-20
```

### **Ежедневный планировщик:**
```bash
source venv/bin/activate
python functions/workdrive_scheduler.py
```
*Запускается в фоне и каждый день в 23:59:59 обрабатывает новые файлы*

## 🔄 **WORKFLOW ОБРАБОТКИ**

### **Для каждого файла:**
1. **📥 Скачивание** из WorkDrive в временную папку
2. **🤖 LLM анализ** через `analyze_proforma_via_agent()`
3. **🔍 Поиск/создание поставщика** в Zoho Books
4. **📊 Создание Bill payload** с правильными line items и taxes
5. **📝 Создание Bill** в Zoho Books (PARKENTERTAINMENT org)
6. **📎 Прикрепление PDF** к созданному Bill
7. **✅ Отметка как обработанный** в `workdrive_processed.json`

### **После обработки всех файлов:**
8. **📱 Telegram отчёт** с результатами и ссылками на Bills

## 📊 **ОТЧЁТЫ TELEGRAM**

### **Успешная обработка:**
```
📊 ОТЧЁТ ОБРАБОТКИ WORKDRIVE за 2025-08-19

✅ УСПЕШНО ОБРАБОТАНО: 3
• FV A/3693/2025 - HIBISPOL SP. Z.O.O.
  Ссылка: https://books.zoho.eu/app/20082562863#/bills/46000123
• FV A/3666/2025 - HIBISPOL SP. Z.O.O.  
  Ссылка: https://books.zoho.eu/app/20082562863#/bills/46000124

🕐 Время: 2025-08-22 23:59:59
```

### **С ошибками:**
```
❌ ОШИБКИ: 1
• GS-0000017-08-2025_17.08.2025.pdf
  Ошибка: Не удалось создать поставщика: NOVA POST...
```

## 🐛 **ОТЛАДКА**

### **Проверка логов:**
```bash
tail -f logs/workdrive_batch.log
```

### **Очистка обработанных файлов (для повторного тестирования):**
```bash
rm -f data/workdrive_processed.json
```

### **Проверка WorkDrive API:**
```bash
source venv/bin/activate
python functions/zoho_workdrive.py
```

## 🔧 **НАСТРОЙКИ**

### **Организация для Bills:**
- По умолчанию: **PARKENTERTAINMENT** (`20082562863`)
- Можно изменить в `determine_organization()` в `workdrive_batch_processor.py`

### **Время запуска:**
- По умолчанию: **23:59:59 Warsaw time**  
- Можно изменить в `workdrive_scheduler.py`

### **Папки WorkDrive:**
- Текущая: **August** (`1zqms56fb76bbe95e469bacc06a33e010fb84`)
- Для других месяцев нужно обновить `august_folder_id` в `ZohoWorkDriveAPI`

## ⚠️ **ВАЖНЫЕ ЗАМЕЧАНИЯ**

1. **Дедупликация**: Файлы обрабатываются только один раз
2. **Формат дат**: Автоматическое преобразование DD.MM.YYYY → YYYY-MM-DD для Zoho
3. **Создание поставщиков**: Система автоматически создаёт новых поставщиков
4. **Временные файлы**: Автоматически удаляются после обработки
5. **Fallback logic**: Если нет line items, создаётся один общий item

## 🎯 **РЕЗУЛЬТАТ**

Система полностью автоматизирует процесс:
- **Каждый день в 23:59:59** обрабатывает новые инвойсы из WorkDrive
- **Создаёт Bills** в Zoho Books с правильными данными
- **Отправляет отчёты** в Telegram с ссылками для проверки
- **Не дублирует** уже обработанные файлы  
- **Обрабатывает ошибки** с детальными логами

**🎉 Готово к продакшн использованию!**


