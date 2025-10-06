# Система мониторинга и метрик

## 🎯 Цель
Создать централизованную систему мониторинга для отслеживания здоровья системы, производительности и бизнес-метрик.

## 📊 Ключевые метрики

### 1. **Операционные метрики**
- **Скорость обработки документов** (документов/час)
- **Процент успешной обработки** (success rate)
- **Среднее время обработки** по типам документов
- **Количество ошибок** по компонентам

### 2. **Бизнес-метрики**
- **Сэкономленное время** vs ручная обработка
- **Точность извлечения данных** (%)
- **Количество автоматически созданных записей**
- **ROI автоматизации**

### 3. **Технические метрики**
- **API Rate Limits** (Zoho, OpenAI, Google)
- **Размер кэша и эффективность**
- **Время отклика endpoints**
- **Использование ресурсов** (CPU, RAM, Storage)

## 🛠 Реализация

### Prometheus + Grafana Stack
```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana
    volumes:
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin

  node_exporter:
    image: prom/node-exporter
    ports:
      - "9100:9100"
```

### Метрики в коде
```python
from prometheus_client import Counter, Histogram, Gauge
import time

# Счетчики
documents_processed = Counter('documents_processed_total', 
                            'Total processed documents', 
                            ['type', 'status'])
api_calls = Counter('api_calls_total', 
                   'Total API calls', 
                   ['service', 'endpoint'])

# Гистограммы
processing_time = Histogram('document_processing_seconds', 
                          'Time to process document',
                          ['document_type'])

# Gauge
cache_size = Gauge('cache_size_bytes', 
                  'Current cache size in bytes',
                  ['cache_type'])

# Использование
@processing_time.labels(document_type='invoice').time()
def process_invoice(file_path):
    # обработка
    documents_processed.labels(type='invoice', status='success').inc()
```

## 📈 Дашборды

### 1. **Operational Dashboard**
- Документов обработано за последние 24ч
- Success/Error rate график
- Среднее время обработки по часам
- Топ-10 ошибок

### 2. **Business Dashboard**
- Сэкономленное время (часы)
- Точность по типам документов
- Тренды обработки по месяцам
- Распределение по организациям

### 3. **Technical Dashboard**
- API rate limits usage
- Cache hit/miss ratio
- Response time percentiles
- System resources

## 🔔 Алерты

```yaml
groups:
  - name: document_processing
    rules:
      - alert: HighErrorRate
        expr: rate(documents_processed_total{status="error"}[5m]) > 0.1
        for: 10m
        annotations:
          summary: "High error rate in document processing"
      
      - alert: SlowProcessing
        expr: histogram_quantile(0.95, document_processing_seconds) > 60
        for: 15m
        annotations:
          summary: "Document processing is slow"
      
      - alert: APIRateLimitNear
        expr: api_rate_limit_remaining < 100
        for: 5m
        annotations:
          summary: "API rate limit nearly exhausted"
```
