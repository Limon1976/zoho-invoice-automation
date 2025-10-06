"""
File validation utilities for safe file handling.
Prevents DoS attacks and memory issues from large files.
"""
import tempfile
import os
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Maximum file size: 50MB
MAX_FILE_SIZE = 50 * 1024 * 1024  

# Supported file types - PDF для прямого парсинга, остальные для OCR
PDF_EXTENSIONS = {'.pdf', '.PDF'}  # Для PDFPlumber
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.bmp'}  # Для Google Vision
ALLOWED_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS


class FileSizeError(ValueError):
    """Raised when file exceeds size limit"""
    pass


class FileTypeError(ValueError):
    """Raised when file type is not allowed"""
    pass


async def validate_and_download(document, context=None) -> str:
    """
    Safely download document with size and type validation.
    
    Args:
        document: Telegram Document object
        context: Bot context (optional)
        
    Returns:
        Path to downloaded temporary file
        
    Raises:
        FileSizeError: If file is too large
        FileTypeError: If file type not allowed
        ValueError: For other validation errors
    """
    # Check file extension - Document имеет file_name
    file_name = document.file_name if hasattr(document, 'file_name') else None
    
    if file_name:
        _, ext = os.path.splitext(file_name)
        if ext not in ALLOWED_EXTENSIONS:
            raise FileTypeError(
                f"Тип файла {ext} не поддерживается. "
                f"Поддерживаются: PDF для прямого парсинга, "
                f"изображения (JPG, PNG, TIFF) для OCR"
            )
    
    # Check file size
    if hasattr(document, 'file_size') and document.file_size:
        if document.file_size > MAX_FILE_SIZE:
            size_mb = document.file_size / (1024 * 1024)
            max_mb = MAX_FILE_SIZE / (1024 * 1024)
            raise FileSizeError(
                f"Файл слишком большой: {size_mb:.1f}MB. "
                f"Максимальный размер: {max_mb:.0f}MB"
            )
        
        logger.info(f"Downloading document: {file_name or 'unknown'} "
                   f"({document.file_size / 1024:.1f}KB)")
    
    # Safe download with temporary file
    try:
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            # Document не имеет download_to_drive, нужно получить File объект
            if hasattr(document, 'get_file'):
                # Получаем File объект из Document
                file = await context.bot.get_file(document.file_id)
                await file.download_to_drive(temp_file.name)
            else:
                # Fallback - пытаемся использовать document напрямую
                await document.download_to_drive(temp_file.name)
                
            temp_path = temp_file.name
            
        # Verify downloaded file size (double-check)
        actual_size = os.path.getsize(temp_path)
        if actual_size > MAX_FILE_SIZE:
            os.unlink(temp_path)  # Clean up
            raise FileSizeError(
                f"Загруженный файл превышает лимит: "
                f"{actual_size / (1024 * 1024):.1f}MB"
            )
            
        logger.info(f"File downloaded successfully: {temp_path}")
        return temp_path
        
    except Exception as e:
        # Clean up on any error
        if 'temp_path' in locals() and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass
        raise


def get_file_size_message(file_size: Optional[int]) -> str:
    """Format file size for user message"""
    if not file_size:
        return "неизвестный размер"
    
    if file_size < 1024:
        return f"{file_size} байт"
    elif file_size < 1024 * 1024:
        return f"{file_size / 1024:.1f} КБ"
    else:
        return f"{file_size / (1024 * 1024):.1f} МБ"


def get_file_type(file_name: str) -> str:
    """Определяет тип файла для выбора метода обработки"""
    _, ext = os.path.splitext(file_name.lower())
    
    if ext in PDF_EXTENSIONS:
        return "pdf"  # Для PDFPlumber
    elif ext in IMAGE_EXTENSIONS:
        return "image"  # Для Google Vision OCR
    else:
        return "unknown"


def is_pdf_file(file_name: str) -> bool:
    """Проверяет, является ли файл PDF"""
    return get_file_type(file_name) == "pdf"


def is_image_file(file_name: str) -> bool:
    """Проверяет, является ли файл изображением"""
    return get_file_type(file_name) == "image"

