# Руководство по развертыванию на внешнем сервере

## 🚀 Варианты развертывания

### 1. **Локальная разработка (текущее состояние)**
- ✅ Подходит для тестирования и разработки
- ❌ Нет доступа из интернета для webhooks
- ❌ Нет отказоустойчивости

### 2. **VPS/Облачный сервер (рекомендуется)**
- ✅ Постоянная работа 24/7
- ✅ Доступность из интернета
- ✅ SSL сертификаты
- ✅ Контроль ресурсов

### 3. **Контейнеризация (Docker)**
- ✅ Изолированная среда
- ✅ Простое масштабирование
- ✅ Воспроизводимые развертывания

## 📋 План миграции на внешний сервер

### Этап 1: Подготовка локального проекта ✅
- [x] Система контактов с кэшированием
- [x] FastAPI сервер с роутерами  
- [x] Webhook endpoints
- [x] Скрипты импорта и настройки

### Этап 2: Контейнеризация 🔄
- [ ] Создать Dockerfile
- [ ] Docker Compose для всей системы
- [ ] Переменные окружения
- [ ] Volumes для данных

### Этап 3: Выбор хостинга 📋
**Рекомендуемые провайдеры:**
- **DigitalOcean** - $6-12/месяц, простота настройки
- **Linode** - $5-10/месяц, хорошая производительность  
- **Hetzner** - €3-8/месяц, отличная цена/качество
- **AWS/GCP** - масштабируемость, но сложнее

### Этап 4: Настройка сервера 🛠️
- [ ] Настройка Ubuntu/Debian
- [ ] Установка Docker и Docker Compose
- [ ] Настройка Nginx как reverse proxy
- [ ] SSL сертификат (Let's Encrypt)
- [ ] Firewall и базовая безопасность

### Этап 5: Развертывание 🚀
- [ ] Загрузка кода на сервер
- [ ] Настройка переменных окружения
- [ ] Запуск контейнеров
- [ ] Импорт контактов
- [ ] Настройка webhooks

## 🐳 Docker конфигурация

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY src/ ./src/
COPY *.py ./

# Создаем папки
RUN mkdir -p data logs

# Запускаем приложение
CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml
```yaml
version: '3.8'

services:
  invoice-automation:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - ZOHO_CLIENT_ID=${ZOHO_CLIENT_ID}
      - ZOHO_CLIENT_SECRET=${ZOHO_CLIENT_SECRET}
      - ZOHO_REFRESH_TOKEN=${ZOHO_REFRESH_TOKEN}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - invoice-automation
    restart: unless-stopped
```

## 🔧 Nginx конфигурация

### nginx.conf
```nginx
events {
    worker_connections 1024;
}

http {
    upstream app {
        server invoice-automation:8000;
    }

    server {
        listen 80;
        server_name your-domain.com;
        
        # Redirect to HTTPS
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl;
        server_name your-domain.com;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;

        location / {
            proxy_pass http://app;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Webhook endpoint
        location /api/contacts/webhook/ {
            proxy_pass http://app;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
```

## 🔐 Переменные окружения

### .env (продакшн)
```bash
# Zoho Books API
ZOHO_CLIENT_ID=your_client_id
ZOHO_CLIENT_SECRET=your_client_secret
ZOHO_REFRESH_TOKEN=your_refresh_token

# OpenAI API
OPENAI_API_KEY=your_openai_key

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Environment
ENVIRONMENT=production
DEBUG=false

# Logging
LOG_LEVEL=INFO
```

## 📝 Скрипт развертывания

### deploy.sh
```bash
#!/bin/bash

echo "🚀 Развертывание Invoice Automation System"

# Обновляем код
git pull origin main

# Останавливаем старые контейнеры
docker-compose down

# Пересобираем образы
docker-compose build --no-cache

# Запускаем новые контейнеры
docker-compose up -d

# Проверяем статус
sleep 10
docker-compose ps

# Импортируем контакты (если нужно)
docker-compose exec invoice-automation python run_contact_import.py

echo "✅ Развертывание завершено"
```

## 🔍 Мониторинг и логи

### Команды для мониторинга:
```bash
# Статус контейнеров
docker-compose ps

# Логи приложения
docker-compose logs -f invoice-automation

# Логи Nginx
docker-compose logs -f nginx

# Использование ресурсов
docker stats

# Тестирование webhook
curl -X POST https://your-domain.com/api/contacts/webhook/zoho \
  -H "Content-Type: application/json" \
  -d '{"event_type": "test"}'
```

## 🔒 Безопасность

### Рекомендации:
1. **Firewall**: Открыть только порты 22, 80, 443
2. **SSH ключи**: Отключить password аутентификацию  
3. **SSL**: Обязательно для продакшена
4. **Backup**: Автоматическое резервное копирование данных
5. **Monitoring**: Настроить алерты при сбоях

### Backup скрипт:
```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
tar -czf "backup_${DATE}.tar.gz" data/ logs/ .env
# Загружаем в облако или удаленный сервер
```

## 📊 Рекомендуемые ресурсы сервера

### Минимальные требования:
- **CPU**: 1 vCPU
- **RAM**: 1-2 GB  
- **Storage**: 20 GB SSD
- **Network**: 1 TB/месяц

### Рекомендуемые:
- **CPU**: 2 vCPU
- **RAM**: 4 GB
- **Storage**: 40 GB SSD  
- **Network**: Unlimited

## 🎯 Следующие шаги

1. **Выберите хостинг-провайдера**
2. **Создайте Docker образы**
3. **Настройте домен и SSL**
4. **Проведите тестовое развертывание**
5. **Настройте мониторинг**
6. **Перенастройте webhooks на новый URL**

## 📞 План обслуживания

### Еженедельно:
- Проверка логов на ошибки
- Мониторинг использования ресурсов  
- Backup данных

### Ежемесячно:
- Обновление зависимостей
- Проверка SSL сертификатов
- Анализ производительности

### По необходимости:
- Масштабирование при росте нагрузки
- Добавление новых функций
- Оптимизация производительности 