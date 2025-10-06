# Расширенная интеграция и API

## 🎯 Цель
Создать универсальный API для интеграции с внешними системами и расширения функциональности.

## 🔌 REST API v2

### OpenAPI спецификация
```yaml
openapi: 3.0.0
info:
  title: Invoice Automation API
  version: 2.0.0
  description: API для автоматизации обработки документов

paths:
  /api/v2/documents:
    post:
      summary: Загрузить документ для обработки
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                file:
                  type: string
                  format: binary
                metadata:
                  type: object
                  properties:
                    source: string
                    priority: string
                    callback_url: string
      responses:
        202:
          description: Документ принят в обработку
          content:
            application/json:
              schema:
                type: object
                properties:
                  task_id: string
                  status: string
                  estimated_time: integer

  /api/v2/documents/{task_id}/status:
    get:
      summary: Получить статус обработки
      parameters:
        - name: task_id
          in: path
          required: true
          schema:
            type: string
      responses:
        200:
          description: Статус обработки
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProcessingStatus'

  /api/v2/integrations/erp:
    post:
      summary: Настроить интеграцию с ERP
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                erp_type:
                  type: string
                  enum: [sap, oracle, dynamics, 1c]
                connection_config:
                  type: object
                mapping_rules:
                  type: array
```

### GraphQL API
```graphql
type Query {
  document(id: ID!): Document
  documents(
    filter: DocumentFilter
    pagination: PaginationInput
  ): DocumentConnection!
  
  analytics(
    dateRange: DateRangeInput!
    groupBy: GroupByOption
  ): AnalyticsData!
}

type Mutation {
  uploadDocument(
    file: Upload!
    metadata: DocumentMetadataInput
  ): UploadResult!
  
  correctExtraction(
    documentId: ID!
    corrections: ExtractionCorrectionInput!
  ): Document!
  
  configureIntegration(
    type: IntegrationType!
    config: JSON!
  ): Integration!
}

type Subscription {
  documentProcessed(userId: ID!): Document!
  processingStatus(taskId: ID!): ProcessingStatus!
}
```

## 🔗 Интеграции с популярными системами

### 1. **ERP системы**

```python
class ERPIntegrationFactory:
    """Фабрика для создания интеграций с ERP"""
    
    def create_integration(self, erp_type: str) -> ERPIntegration:
        integrations = {
            'sap': SAPIntegration(),
            'oracle': OracleERPIntegration(),
            'dynamics': DynamicsIntegration(),
            '1c': OneCIntegration(),
            'odoo': OdooIntegration()
        }
        
        return integrations.get(erp_type)

class SAPIntegration:
    """Интеграция с SAP"""
    
    async def sync_document(self, document_data: dict):
        """Синхронизирует документ с SAP"""
        
        # Маппинг полей
        sap_document = self._map_to_sap_format(document_data)
        
        # Создание в SAP
        async with SAPClient(self.config) as client:
            result = await client.create_invoice(sap_document)
            
            # Обратная синхронизация ID
            await self._update_local_reference(
                document_data['id'],
                result['sap_id']
            )
```

### 2. **Бухгалтерские системы**

```python
class AccountingIntegrations:
    """Интеграции с бухгалтерскими системами"""
    
    integrations = {
        'quickbooks': QuickBooksIntegration(),
        'xero': XeroIntegration(),
        'freshbooks': FreshBooksIntegration(),
        'wave': WaveIntegration()
    }
    
    async def sync_to_all(self, document_data: dict):
        """Синхронизация со всеми настроенными системами"""
        
        results = {}
        for name, integration in self.integrations.items():
            if integration.is_configured():
                try:
                    result = await integration.sync(document_data)
                    results[name] = {'status': 'success', 'data': result}
                except Exception as e:
                    results[name] = {'status': 'error', 'error': str(e)}
        
        return results
```

### 3. **Облачные хранилища**

```python
class CloudStorageManager:
    """Управление документами в облачных хранилищах"""
    
    def __init__(self):
        self.storages = {
            'google_drive': GoogleDriveStorage(),
            'dropbox': DropboxStorage(),
            'onedrive': OneDriveStorage(),
            's3': S3Storage()
        }
    
    async def auto_backup(self, document_path: str, metadata: dict):
        """Автоматическое резервное копирование"""
        
        # Определяем активные хранилища
        active_storages = [s for s in self.storages.values() if s.is_active()]
        
        # Загружаем параллельно
        tasks = []
        for storage in active_storages:
            task = storage.upload(document_path, metadata)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
```

## 🔄 Webhook система

```python
class WebhookManager:
    """Управление исходящими webhooks"""
    
    def __init__(self):
        self.subscribers = []
        self.retry_policy = RetryPolicy(max_attempts=3)
    
    async def register_webhook(self, 
                              url: str,
                              events: List[str],
                              secret: str):
        """Регистрация нового webhook"""
        
        subscriber = {
            'id': str(uuid.uuid4()),
            'url': url,
            'events': events,
            'secret': secret,
            'created_at': datetime.now(),
            'active': True
        }
        
        self.subscribers.append(subscriber)
        return subscriber['id']
    
    async def trigger_event(self, event_type: str, payload: dict):
        """Отправка события всем подписчикам"""
        
        # Фильтруем подписчиков
        relevant_subscribers = [
            s for s in self.subscribers 
            if event_type in s['events'] and s['active']
        ]
        
        # Отправляем параллельно
        tasks = []
        for subscriber in relevant_subscribers:
            task = self._send_webhook(subscriber, event_type, payload)
            tasks.append(task)
        
        await asyncio.gather(*tasks, return_exceptions=True)
```

## 📱 SDK для разных языков

### Python SDK
```python
# invoice_automation_sdk.py
class InvoiceAutomationClient:
    """Python SDK для Invoice Automation API"""
    
    def __init__(self, api_key: str, base_url: str = None):
        self.api_key = api_key
        self.base_url = base_url or "https://api.invoice-automation.com"
        self.session = httpx.AsyncClient()
    
    async def upload_document(self, 
                            file_path: str,
                            metadata: dict = None) -> dict:
        """Загружает документ для обработки"""
        
        with open(file_path, 'rb') as f:
            files = {'file': f}
            data = {'metadata': json.dumps(metadata)} if metadata else {}
            
            response = await self.session.post(
                f"{self.base_url}/api/v2/documents",
                files=files,
                data=data,
                headers={'Authorization': f'Bearer {self.api_key}'}
            )
            
        return response.json()
```

### JavaScript/TypeScript SDK
```typescript
// invoice-automation-sdk.ts
export class InvoiceAutomationClient {
  constructor(
    private apiKey: string,
    private baseUrl: string = 'https://api.invoice-automation.com'
  ) {}

  async uploadDocument(
    file: File,
    metadata?: DocumentMetadata
  ): Promise<UploadResult> {
    const formData = new FormData();
    formData.append('file', file);
    if (metadata) {
      formData.append('metadata', JSON.stringify(metadata));
    }

    const response = await fetch(`${this.baseUrl}/api/v2/documents`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.apiKey}`
      },
      body: formData
    });

    return response.json();
  }
}
```

## 🔐 Безопасность API

### Rate Limiting
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/v2/documents")
@limiter.limit("10/minute")
async def upload_document(request: Request):
    # Обработка
    pass
```

### API Key Management
```python
class APIKeyManager:
    """Управление API ключами"""
    
    def generate_api_key(self, user_id: str, scopes: List[str]) -> str:
        """Генерирует новый API ключ"""
        
        key_data = {
            'user_id': user_id,
            'scopes': scopes,
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(days=365)).isoformat()
        }
        
        # Шифруем данные
        token = jwt.encode(key_data, settings.SECRET_KEY, algorithm='HS256')
        
        # Сохраняем в базу
        self._save_api_key(user_id, token, scopes)
        
        return token
```

## 📊 API Analytics

```python
class APIAnalytics:
    """Аналитика использования API"""
    
    async def track_request(self, 
                          endpoint: str,
                          user_id: str,
                          response_time: float,
                          status_code: int):
        """Отслеживает API запрос"""
        
        await self.redis.hincrby(
            f"api:stats:{datetime.now().strftime('%Y-%m-%d')}",
            f"{endpoint}:{status_code}",
            1
        )
        
        await self.redis.lpush(
            f"api:response_times:{endpoint}",
            response_time
        )
```
