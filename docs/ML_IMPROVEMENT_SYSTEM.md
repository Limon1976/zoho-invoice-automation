# Система машинного обучения для улучшения точности

## 🎯 Цель
Постоянно улучшать точность извлечения данных через обучение на исправлениях пользователей.

## 🧠 Компоненты ML системы

### 1. **Сбор обучающих данных**

```python
class TrainingDataCollector:
    """Собирает данные из исправлений пользователей"""
    
    def __init__(self):
        self.training_data = []
        self.validation_threshold = 100  # Минимум для обучения
    
    async def collect_correction(self, 
                                original_extraction: dict,
                                user_correction: dict,
                                document_path: str):
        """Сохраняет исправление как обучающий пример"""
        
        # Извлекаем features из документа
        features = await self._extract_features(document_path)
        
        training_example = {
            'features': features,
            'original': original_extraction,
            'corrected': user_correction,
            'timestamp': datetime.now(),
            'document_type': self._classify_document(document_path)
        }
        
        self.training_data.append(training_example)
        
        # Проверяем, достаточно ли данных для обучения
        if len(self.training_data) >= self.validation_threshold:
            await self._trigger_retraining()
```

### 2. **Feature Engineering**

```python
class DocumentFeatureExtractor:
    """Извлекает признаки из документов для ML"""
    
    def extract_features(self, document_text: str) -> dict:
        """Извлекает структурированные признаки"""
        
        features = {
            # Текстовые признаки
            'text_length': len(document_text),
            'line_count': document_text.count('\n'),
            'has_table': self._detect_table_structure(document_text),
            
            # Паттерны
            'vat_pattern_found': bool(re.search(r'[A-Z]{2}\d{8,12}', document_text)),
            'date_patterns': len(re.findall(r'\d{2}[-/.]\d{2}[-/.]\d{4}', document_text)),
            'amount_patterns': len(re.findall(r'\d+[.,]\d{2}', document_text)),
            
            # Ключевые слова
            'invoice_keywords': self._count_keywords(document_text, INVOICE_KEYWORDS),
            'company_indicators': self._count_keywords(document_text, COMPANY_KEYWORDS),
            
            # Структура
            'header_confidence': self._analyze_header_structure(document_text),
            'footer_confidence': self._analyze_footer_structure(document_text),
            
            # Язык
            'detected_language': self._detect_language(document_text),
            'language_confidence': self._language_confidence(document_text)
        }
        
        return features
```

### 3. **Модели для разных задач**

```python
class SpecializedModels:
    """Специализированные модели для разных типов данных"""
    
    def __init__(self):
        self.models = {
            'company_matcher': CompanyMatchingModel(),
            'amount_extractor': AmountExtractionModel(),
            'date_parser': DateParsingModel(),
            'vat_validator': VATValidationModel(),
            'document_classifier': DocumentTypeClassifier()
        }
    
    async def train_all(self, training_data: list):
        """Обучает все модели на новых данных"""
        
        for model_name, model in self.models.items():
            # Фильтруем данные релевантные для модели
            relevant_data = self._filter_relevant_data(
                training_data, 
                model_name
            )
            
            if len(relevant_data) > model.min_training_size:
                await model.train(relevant_data)
                
                # Валидация на тестовой выборке
                metrics = await model.validate()
                
                # Деплой только если улучшение
                if metrics['accuracy'] > model.current_accuracy:
                    await model.deploy()
```

### 4. **Active Learning**

```python
class ActiveLearningManager:
    """Управляет активным обучением - запрашивает разметку сложных случаев"""
    
    def __init__(self):
        self.uncertainty_threshold = 0.3
        self.ambiguous_cases = []
    
    async def process_with_uncertainty(self, document_path: str) -> dict:
        """Обрабатывает документ и определяет неуверенность"""
        
        # Получаем предсказания от всех моделей
        predictions = await self._get_all_predictions(document_path)
        
        # Вычисляем неуверенность
        uncertainty = self._calculate_uncertainty(predictions)
        
        if uncertainty > self.uncertainty_threshold:
            # Добавляем в очередь для ручной проверки
            await self._queue_for_review(document_path, predictions, uncertainty)
            
            # Уведомляем пользователя
            await self._notify_review_needed(
                document_path,
                reason="Low confidence extraction"
            )
        
        return predictions['best_guess']
```

### 5. **A/B тестирование моделей**

```python
class ModelABTester:
    """A/B тестирование новых моделей в продакшене"""
    
    def __init__(self):
        self.experiments = {}
        self.traffic_split = 0.1  # 10% на новую модель
    
    async def process_with_experiment(self, document_path: str) -> dict:
        """Обрабатывает документ с A/B тестом"""
        
        # Определяем, использовать ли экспериментальную модель
        use_experimental = random.random() < self.traffic_split
        
        if use_experimental and self.experiments:
            model = self.experiments['current']
            result = await model.process(document_path)
            
            # Логируем для анализа
            await self._log_experiment_result(
                document_path,
                model_version='experimental',
                result=result
            )
        else:
            model = self.production_model
            result = await model.process(document_path)
            
            await self._log_experiment_result(
                document_path,
                model_version='production',
                result=result
            )
        
        return result
```

## 📊 Метрики качества

### Отслеживаемые метрики:
1. **Precision/Recall** по типам полей
2. **F1 Score** для общей оценки
3. **Confusion Matrix** для типов документов
4. **User Correction Rate** - частота исправлений
5. **Processing Confidence** - уверенность модели

### Dashboard для мониторинга:
```python
class MLMetricsDashboard:
    """Дашборд для отслеживания ML метрик"""
    
    def generate_report(self) -> dict:
        return {
            'model_performance': {
                'company_matching': {
                    'accuracy': 0.95,
                    'precision': 0.93,
                    'recall': 0.97,
                    'f1_score': 0.95
                },
                'amount_extraction': {
                    'accuracy': 0.98,
                    'mean_error': 0.02,
                    'outliers': 3
                }
            },
            'training_stats': {
                'total_examples': 5420,
                'last_training': '2024-01-15',
                'next_scheduled': '2024-02-01'
            },
            'user_feedback': {
                'correction_rate': 0.05,
                'satisfaction_score': 4.7
            }
        }
```

## 🚀 Развертывание улучшений

### CI/CD pipeline для ML:
1. **Автоматическое переобучение** при накоплении данных
2. **Валидация на тестовом наборе**
3. **Canary deployment** - постепенный rollout
4. **Откат при деградации метрик**

```yaml
# .github/workflows/ml-pipeline.yml
name: ML Model Training Pipeline

on:
  schedule:
    - cron: '0 2 * * 0'  # Еженедельно
  workflow_dispatch:

jobs:
  train:
    runs-on: ubuntu-latest
    steps:
      - name: Prepare training data
        run: python scripts/prepare_training_data.py
      
      - name: Train models
        run: python scripts/train_models.py
      
      - name: Validate performance
        run: python scripts/validate_models.py
      
      - name: Deploy if improved
        if: success()
        run: python scripts/deploy_models.py
```
