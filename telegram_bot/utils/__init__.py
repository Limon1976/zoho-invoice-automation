"""
Utility modules for Telegram bot.
Contains thread-safe implementations and validation utilities.
"""

from .callback_deduplicator import callback_deduplicator, CallbackDeduplicator
from .file_validator import (
    validate_and_download, 
    FileSizeError, 
    FileTypeError,
    MAX_FILE_SIZE,
    get_file_size_message,
    get_file_type,
    is_pdf_file,
    is_image_file,
    PDF_EXTENSIONS,
    IMAGE_EXTENSIONS
)

__all__ = [
    'callback_deduplicator',
    'CallbackDeduplicator',
    'validate_and_download',
    'FileSizeError', 
    'FileTypeError',
    'MAX_FILE_SIZE',
    'get_file_size_message',
    'get_file_type',
    'is_pdf_file',
    'is_image_file',
    'PDF_EXTENSIONS',
    'IMAGE_EXTENSIONS'
]

