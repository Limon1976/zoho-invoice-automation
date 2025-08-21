import logging
from mcp_connector.ocr_utils import ocr_pdf_google


def _try_native_pdf_text(pdf_path: str) -> str:
    """Пытается извлечь текстовый слой из PDF (если есть) без OCR.
    Возвращает пустую строку при неудаче.
    """
    # Попытка через pdfminer.six
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract
        logging.info("🧪 Пробую извлечь текстовый слой через pdfminer...")
        native_text = pdfminer_extract(pdf_path) or ""
        if native_text and len(native_text.strip()) >= 300:
            logging.info("✅ Найден текстовый слой (pdfminer), длина=%d", len(native_text))
            return native_text
    except Exception as e:
        logging.info(f"ℹ️ pdfminer недоступен/ошибка: {e}")

    # Попытка через PyPDF2 как лёгкий фолбэк
    try:
        import PyPDF2  # type: ignore
        logging.info("🧪 Пробую извлечь текстовый слой через PyPDF2...")
        txt_parts = []
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                t = page.extract_text() or ""
                if t:
                    txt_parts.append(t)
        native_text = "\n".join(txt_parts)
        if native_text and len(native_text.strip()) >= 300:
            logging.info("✅ Найден текстовый слой (PyPDF2), длина=%d", len(native_text))
            return native_text
    except Exception as e:
        logging.info(f"ℹ️ PyPDF2 недоступен/ошибка: {e}")

    return ""


def extract_text_from_pdf(pdf_path):
    """
    УМНАЯ ЛОГИКА: Сначала проверяем текстовый слой, потом OCR только для сканов.
    1. Если есть текстовый слой → используем нативное извлечение
    2. Если скан без текста → используем Google Vision OCR
    """
    # 🎯 ШАГ 1: Проверяем текстовый слой
    logging.info("🔍 Проверяю наличие текстового слоя в PDF...")
    native_text = _try_native_pdf_text(pdf_path)
    
    if native_text:
        logging.info(f"✅ ТЕКСТОВЫЙ СЛОЙ НАЙДЕН! Длина: {len(native_text)} символов")
        logging.info("📄 NATIVE TEXT (первые 1000 символов):\n%s", native_text[:1000])
        return native_text.strip()
    else:
        # 🎯 ШАГ 2: Нет текстового слоя → используем OCR для скана
        logging.info("❌ Текстовый слой не найден. Запускаю Google Vision OCR для скана...")
        text = ocr_pdf_google(pdf_path)
        logging.info("📄 OCR RAW (первые 1000 символов):\n%s", text[:1000])
        return text.strip()