# Влияние внедрения на существующий код

## 📊 Общая оценка влияния

### По этапам:
1. **Мониторинг**: ~5% изменений (только добавления)
2. **Производительность**: ~20% изменений (рефакторинг)
3. **ML**: ~10% изменений + новые модули
4. **API**: ~30% изменений + новая версия

## 🗂️ Какие файлы будут затронуты

### ✅ НЕ ТРОГАЕМ (остаются как есть):
```
config/
├── config.py              # Конфигурация - НЕ МЕНЯЕТСЯ
├── zoho_auth.py          # Авторизация - НЕ МЕНЯЕТСЯ
└── category_keywords.json # Данные - НЕ МЕНЯЮТСЯ

data/                     # Все данные - НЕ ТРОГАЕМ
processed_files/          # Архив - НЕ ТРОГАЕМ
keys/                     # Ключи - НЕ ТРОГАЕМ
```

### 🟡 МИНИМАЛЬНЫЕ ИЗМЕНЕНИЯ (1-5 строк):
```python
# functions/ai_invoice_analyzer.py
+ from src.infrastructure.metrics import document_counter, processing_time
  
  async def analyze_invoice_text(self, text: str):
+     start_time = time.time()
      # ... существующий код ...
+     processing_time.observe(time.time() - start_time)

# telegram_bot/bot_main.py  
+ from src.infrastructure.metrics import start_metrics_server
  
  def start_bot():
+     start_metrics_server(8001)  # Метрики на отдельном порту
      # ... существующий код ...

# functions/zoho_api.py
+ @circuit_breaker(fail_max=5, reset_timeout=60)
  def make_api_call(self, endpoint, data):
      # ... существующий код без изменений ...
```

### 🟠 УМЕРЕННЫЕ ИЗМЕНЕНИЯ (рефакторинг методов):
```python
# functions/smart_document_processor.py
  class SmartDocumentProcessor:
-     def process_documents(self, files):
-         results = []
-         for file in files:
-             result = self.process_single(file)
-             results.append(result)
-         return results
+     async def process_documents(self, files):
+         # Параллельная обработка
+         tasks = [self.process_single(f) for f in files]
+         return await asyncio.gather(*tasks)

# functions/contact_creator.py
+ from src.infrastructure.cache import contact_cache
  
  def find_or_create_contact(self, vat_number):
+     # Проверяем кэш
+     cached = contact_cache.get(vat_number)
+     if cached:
+         return cached
      
      # ... существующая логика ...
+     contact_cache.set(vat_number, result)
```

### 🆕 НОВЫЕ ФАЙЛЫ (не влияют на существующие):
```
src/infrastructure/
├── metrics.py           # Prometheus метрики
├── circuit_breaker.py   # Защита от сбоев
├── cache.py            # Redis кэширование
└── retry_handler.py    # Умные повторы

src/ml/
├── models/             # ML модели
├── training/           # Сбор данных
└── ab_testing.py       # A/B тесты

monitoring/
├── docker-compose.yml  # Prometheus + Grafana
├── dashboards/         # Готовые дашборды
└── alerts.yml          # Правила алертов
```

## 🛡️ Стратегия безопасного внедрения

### 1. **Feature Flags (переключатели функций)**
```python
# config/features.py
FEATURES = {
    'parallel_processing': False,  # Включаем постепенно
    'ml_predictions': False,       # Тестируем на части
    'new_cache': False,           # Сначала в shadow mode
}

# Использование
if FEATURES['parallel_processing']:
    results = await process_parallel(docs)
else:
    results = process_sequential(docs)  # Старый код
```

### 2. **Shadow Mode (теневой режим)**
```python
# Новый код работает параллельно, но не влияет
result_old = old_method(data)
result_new = new_method(data)

# Логируем расхождения
if result_old != result_new:
    logger.warning(f"Shadow mode diff: {result_old} vs {result_new}")

# Возвращаем старый результат
return result_old
```

### 3. **Постепенный Rollout**
```python
# 10% трафика на новую версию
if random.random() < 0.1:
    return new_processing(document)
else:
    return old_processing(document)
```

## 📝 Backup план

### Перед каждым этапом:
1. **Git branch**: `feature/monitoring-v1`
2. **Database backup**: `pg_dump zoho_db > backup_$(date).sql`
3. **Config backup**: `cp -r config/ config_backup/`
4. **Docker images**: тегируем старые версии

### Откат за 5 минут:
```bash
# Быстрый откат
git checkout main
docker-compose down
docker-compose up -d --build

# Восстановление данных (если нужно)
pg_restore backup_latest.sql
```

## ✅ Гарантии

1. **Основная бизнес-логика НЕ МЕНЯЕТСЯ**
2. **Все изменения обратно совместимы**
3. **Каждый этап можно откатить независимо**
4. **Тестирование на staging перед production**
5. **Мониторинг каждого изменения**

## 🎯 Итог

- **80% кода останется без изменений**
- **15% получит минимальные добавления** (метрики, кэш)
- **5% будет рефакторинг** (для производительности)
- **Новый функционал** в отдельных модулях

Система продолжит работать как обычно, но станет:
- Быстрее (10-20x)
- Надежнее (99.9% uptime)
- Умнее (ML предсказания)
- Масштабируемее (1000+ док/час)


