# Система обработки ошибок и восстановления

## 🎯 Цель
Создать надежную систему обработки ошибок с автоматическим восстановлением и минимальным вмешательством человека.

## 🔄 Стратегии восстановления

### 1. **Retry стратегии**

```python
from tenacity import retry, stop_after_attempt, wait_exponential
import asyncio

class SmartRetryHandler:
    """Умная система повторных попыток с учетом типа ошибки"""
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60)
    )
    async def process_with_retry(self, document_path: str):
        try:
            return await self._process_document(document_path)
        except RateLimitError:
            # Для rate limit ждем дольше
            await asyncio.sleep(300)  # 5 минут
            raise
        except NetworkError:
            # Сетевые ошибки - быстрый retry
            await asyncio.sleep(5)
            raise
        except ValidationError:
            # Ошибки валидации не повторяем
            await self._move_to_manual_queue(document_path)
            raise
```

### 2. **Очередь для ручной обработки**

```python
class ManualProcessingQueue:
    """Очередь документов требующих ручного вмешательства"""
    
    def __init__(self):
        self.queue = []
        self.reasons = {}
    
    async def add_document(self, 
                          document_path: str, 
                          error_type: str,
                          error_details: dict):
        """Добавляет документ в очередь с контекстом ошибки"""
        
        entry = {
            "document": document_path,
            "error_type": error_type,
            "error_details": error_details,
            "timestamp": datetime.now(),
            "attempts": await self._get_attempt_count(document_path)
        }
        
        self.queue.append(entry)
        
        # Уведомление в Telegram
        await self._notify_manual_required(entry)
```

### 3. **Fallback обработчики**

```python
class FallbackProcessors:
    """Альтернативные методы обработки при сбое основных"""
    
    async def process_with_fallbacks(self, document_path: str):
        """Пробует различные методы обработки по порядку"""
        
        processors = [
            self._process_with_ai,      # OpenAI GPT-4
            self._process_with_ocr,     # Google Vision
            self._process_with_regex,   # Regex patterns
            self._process_manually      # Ручная обработка
        ]
        
        for processor in processors:
            try:
                result = await processor(document_path)
                if result.confidence > 0.7:
                    return result
            except Exception as e:
                logger.warning(f"Fallback failed: {processor.__name__}", error=e)
                continue
        
        raise AllProcessorsFailed(document_path)
```

## 🏥 Health Check система

```python
class HealthMonitor:
    """Мониторинг здоровья компонентов системы"""
    
    def __init__(self):
        self.components = {
            'zoho_api': ZohoHealthCheck(),
            'openai_api': OpenAIHealthCheck(),
            'google_vision': GoogleVisionHealthCheck(),
            'telegram_bot': TelegramHealthCheck(),
            'database': DatabaseHealthCheck()
        }
    
    async def check_all(self) -> dict:
        """Проверяет все компоненты"""
        results = {}
        
        for name, checker in self.components.items():
            try:
                status = await checker.check()
                results[name] = {
                    'status': status,
                    'last_check': datetime.now()
                }
            except Exception as e:
                results[name] = {
                    'status': 'unhealthy',
                    'error': str(e),
                    'last_check': datetime.now()
                }
        
        return results
```

## 🔧 Circuit Breaker паттерн

```python
from circuit_breaker import CircuitBreaker

class APICircuitBreaker:
    """Предотвращает перегрузку сбойных сервисов"""
    
    def __init__(self):
        self.breakers = {
            'zoho': CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=60,
                expected_exception=ZohoAPIError
            ),
            'openai': CircuitBreaker(
                failure_threshold=3,
                recovery_timeout=30,
                expected_exception=OpenAIError
            )
        }
    
    async def call_api(self, service: str, func, *args, **kwargs):
        """Вызов API через circuit breaker"""
        
        breaker = self.breakers.get(service)
        if not breaker:
            return await func(*args, **kwargs)
        
        return await breaker.call(func, *args, **kwargs)
```

## 📊 Логирование ошибок

```python
import structlog
from elasticsearch import AsyncElasticsearch

class ErrorLogger:
    """Централизованное логирование ошибок"""
    
    def __init__(self):
        self.logger = structlog.get_logger()
        self.es = AsyncElasticsearch(['localhost:9200'])
    
    async def log_error(self, 
                       error_type: str,
                       error_details: dict,
                       context: dict):
        """Логирует ошибку с полным контекстом"""
        
        error_doc = {
            'timestamp': datetime.now(),
            'error_type': error_type,
            'error_details': error_details,
            'context': context,
            'stack_trace': traceback.format_exc(),
            'environment': os.getenv('ENVIRONMENT', 'development')
        }
        
        # Локальное логирование
        self.logger.error(
            "Processing error occurred",
            **error_doc
        )
        
        # Отправка в Elasticsearch для анализа
        await self.es.index(
            index='errors',
            body=error_doc
        )
```

## 🚨 Система уведомлений

```python
class AlertManager:
    """Управление уведомлениями об ошибках"""
    
    def __init__(self):
        self.channels = {
            'telegram': TelegramAlertChannel(),
            'email': EmailAlertChannel(),
            'slack': SlackAlertChannel()
        }
        
        self.alert_rules = [
            {
                'condition': lambda e: e.error_count > 10,
                'channels': ['telegram', 'email'],
                'severity': 'critical'
            },
            {
                'condition': lambda e: isinstance(e, APIRateLimitError),
                'channels': ['telegram'],
                'severity': 'warning'
            }
        ]
    
    async def check_and_alert(self, error_stats: dict):
        """Проверяет условия и отправляет алерты"""
        
        for rule in self.alert_rules:
            if rule['condition'](error_stats):
                await self._send_alerts(
                    rule['channels'],
                    rule['severity'],
                    error_stats
                )
```

## 📈 Метрики восстановления

- **MTTR (Mean Time To Recovery)** - среднее время восстановления
- **Success Rate после retry** - процент успешных повторных попыток
- **Manual Queue Size** - размер очереди ручной обработки
- **Circuit Breaker State** - состояние предохранителей
