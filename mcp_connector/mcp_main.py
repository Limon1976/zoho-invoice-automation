

from mcp_connector.pdf_parser import extract_text_from_pdf
from mcp_connector.invoice_router import route_document

def process_file(pdf_path):
    """
    Основная функция MCP-коннектора:
    - Получает путь к PDF
    - Извлекает текст (или запускает OCR, если потребуется)
    - Маршрутизирует документ (определяет тип и парсит поля)
    - Возвращает dataclass (Proforma или Invoice), либо None
    """
    # 1. Извлекаем текст из PDF
    text = extract_text_from_pdf(pdf_path)
    if not text or len(text.strip()) == 0:
        print("❗️Ошибка: Не удалось извлечь текст из PDF.")
        return None

    # 2. Маршрутизируем и парсим документ
    parsed_obj = route_document(text)
    if parsed_obj is None:
        print("❗️Документ не распознан или содержит недостаточно данных.")
        return None

    # 3. Можно тут добавить логи/валидацию или подготовить к отправке в Zoho
    print("✅ MCP-коннектор успешно обработал документ:")
    print(parsed_obj)
    return parsed_obj

# Для теста вручную:
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Использование: python mcp_main.py path/to/file.pdf")
    else:
        process_file(sys.argv[1])