import logging
from mcp_connector.ocr_utils import ocr_pdf_google

def extract_text_from_pdf(pdf_path):
    """
    ВСЕГДА извлекает текст из PDF через Google Vision OCR.
    """
    logging.info("📤 Отправляю PDF в Google Vision OCR...")
    text = ocr_pdf_google(pdf_path)
    logging.info("📄 OCR RAW (первые 3000 символов):\n%s", text[:3000])
    return text.strip()