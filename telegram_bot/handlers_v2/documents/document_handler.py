"""
Новый Document Handler v2 с поддержкой JPEG и чистой архитектурой
"""

import logging
import tempfile
import os
from pathlib import Path
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes

from telegram_bot.handlers_v2.base import BaseHandler, SafetyMixin, ValidationMixin
from telegram_bot.utils_v2.feature_flags import is_enabled
from functions.agent_invoice_parser import analyze_proforma_via_agent

logger = logging.getLogger(__name__)


class DocumentHandlerV2(BaseHandler, SafetyMixin, ValidationMixin):
    """Новый обработчик документов с поддержкой PDF и JPEG"""
    
    def __init__(self):
        super().__init__()
        self.supported_formats = {
            'pdf': self._process_pdf,
            'jpeg': self._process_image,
            'jpg': self._process_image,
            'png': self._process_image,
            'tiff': self._process_image
        }
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Универсальный обработчик документов"""
        
        # Проверяем feature flag
        if not self.should_use_new_handler('document'):
            await self.fallback_to_old_handler(update, context, 'document_handler')
            return
        
        try:
            # Backup контекста для безопасности
            await self.backup_context(context, 'document_processing')
            
            # Определяем тип файла
            file_info = await self._get_file_info(update)
            if not file_info:
                await update.message.reply_text("❌ Не удалось получить информацию о файле")
                return
            
            file_type = file_info['type']
            file_path = file_info['path']
            
            # Проверяем поддержку формата
            if file_type not in self.supported_formats:
                await update.message.reply_text(
                    f"❌ Неподдерживаемый формат: {file_type}\n"
                    f"✅ Поддерживаемые: {', '.join(self.supported_formats.keys())}"
                )
                return
            
            # Обрабатываем документ
            await update.message.reply_text("🔄 Обрабатываю документ...")
            
            processor = self.supported_formats[file_type]
            result = await processor(file_path)
            
            # Валидируем результат
            if not result or not self.validate_analysis(result.get('document_analysis', {})):
                await update.message.reply_text("❌ Ошибка анализа документа")
                return
            
            # Сохраняем результат в контексте
            context.user_data['document_analysis_v2'] = result.get('document_analysis')
            context.user_data['smart_result_v2'] = result
            
            # Формируем ответ
            message = self._format_analysis_message(result.get('document_analysis', {}))
            keyboard = self._build_action_keyboard(result.get('document_analysis', {}))
            
            await update.message.reply_text(message, reply_markup=keyboard)
            
            logger.info(f"✅ Документ обработан через handlers_v2: {file_info['name']}")
            
        except Exception as e:
            await self.handle_error(update, e, "обработки документа")
    
    async def _get_file_info(self, update: Update) -> Optional[dict]:
        """Получает информацию о файле из update"""
        try:
            if update.message.document:
                # PDF файл
                file = update.message.document
                file_name = file.file_name or 'document.pdf'
                file_type = Path(file_name).suffix.lower().lstrip('.')
                
                # Скачиваем файл
                with tempfile.NamedTemporaryFile(suffix=f'.{file_type}', delete=False) as temp_file:
                    await file.download_to_drive(temp_file.name)
                    
                return {
                    'name': file_name,
                    'type': file_type,
                    'path': temp_file.name,
                    'size': file.file_size
                }
            
            elif update.message.photo:
                # Изображение
                photo = update.message.photo[-1]  # Берем наибольшее разрешение
                file_name = f"photo_{photo.file_id}.jpg"
                
                # Скачиваем изображение
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                    await photo.download_to_drive(temp_file.name)
                    
                return {
                    'name': file_name,
                    'type': 'jpeg',
                    'path': temp_file.name,
                    'size': photo.file_size
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения файла: {e}")
            return None
    
    async def _process_pdf(self, file_path: str) -> dict:
        """Обработка PDF файла"""
        logger.info(f"📄 Обработка PDF: {file_path}")
        
        # Используем существующую проверенную логику
        result = analyze_proforma_via_agent(file_path)
        
        return result
    
    async def _process_image(self, image_path: str) -> dict:
        """Обработка изображения с конвертацией в PDF"""
        logger.info(f"📸 Обработка изображения: {image_path}")
        
        # Конвертируем в PDF (используя готовую логику из handlers)
        pdf_path = await self._convert_image_to_pdf(image_path)
        
        # Обрабатываем как PDF
        result = await self._process_pdf(pdf_path)
        
        # Сохраняем путь к PDF для прикрепления
        result['processed_file_path'] = pdf_path
        
        return result
    
    async def _convert_image_to_pdf(self, image_path: str) -> str:
        """Конвертирует изображение в PDF (готовая логика из handlers)"""
        try:
            from PIL import Image
            
            # Открываем изображение
            image = Image.open(image_path)
            
            # Конвертируем в RGB если нужно
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Создаем PDF
            pdf_path = image_path.replace('.jpg', '.pdf').replace('.jpeg', '.pdf').replace('.png', '.pdf')
            image.save(pdf_path, "PDF", resolution=100.0)
            
            logger.info(f"📄 Изображение сконвертировано в PDF: {pdf_path}")
            return pdf_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка конвертации изображения: {e}")
            raise
    
    def _format_analysis_message(self, analysis: dict) -> str:
        """Форматирует сообщение с результатами анализа"""
        if not analysis:
            return "❌ Анализ документа не удался"
        
        message = "📄 АНАЛИЗ ДОКУМЕНТА (v2)\n\n"
        
        # Поставщик
        supplier_name = analysis.get('supplier_name', 'Не определен')
        supplier_vat = analysis.get('supplier_vat', 'Не указан')
        message += f"🏪 Поставщик: {supplier_name}\n"
        message += f"🏷️ VAT: {supplier_vat}\n"
        
        # Сумма
        total_amount = analysis.get('total_amount', 0)
        currency = analysis.get('currency', 'PLN')
        message += f"💰 Сумма: {total_amount} {currency}\n"
        
        # Дата
        document_date = analysis.get('document_date', 'Не определена')
        message += f"📅 Дата: {document_date}\n"
        
        # Тип документа
        document_type = analysis.get('document_type', 'Не определен')
        message += f"📋 Тип: {document_type}\n"
        
        # Организация
        our_company = analysis.get('our_company', {})
        if our_company:
            message += f"🏢 Наша организация: {our_company.get('name', 'Не определена')}\n"
        
        message += "\n🎯 Выберите действие:"
        
        return message
    
    def _build_action_keyboard(self, analysis: dict):
        """Строит клавиатуру с действиями"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = []
        
        # Определяем доступные действия
        document_type = (analysis.get('document_type', '') or '').lower()
        
        if document_type == 'receipt':
            # Для чеков - создание Expense
            keyboard.append([
                InlineKeyboardButton("💳 Создать Expense", callback_data="v2_create_expense")
            ])
        else:
            # Для инвойсов - создание Bill
            keyboard.append([
                InlineKeyboardButton("📋 Создать Bill", callback_data="v2_create_bill")
            ])
        
        # Общие действия
        keyboard.append([
            InlineKeyboardButton("👤 Создать контакт", callback_data="v2_create_contact")
        ])
        
        keyboard.append([
            InlineKeyboardButton("📁 Загрузить в WorkDrive", callback_data="v2_upload_workdrive")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    async def cleanup_temp_files(self, *file_paths):
        """Очищает временные файлы"""
        for file_path in file_paths:
            try:
                if file_path and os.path.exists(file_path):
                    os.unlink(file_path)
                    logger.info(f"🗑️ Удален временный файл: {file_path}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось удалить временный файл {file_path}: {e}")
