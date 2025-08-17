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
    Принудительно используем Google Vision OCR как основной источник (по требованию пользователя).
    """
    logging.info("📤 Отправляю PDF в Google Vision OCR...")
    text = ocr_pdf_google(pdf_path)
    logging.info("📄 OCR RAW (первые 3000 символов):\n%s", text[:3000])
    return text.strip()