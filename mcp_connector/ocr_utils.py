import logging
from google.cloud import vision
import io

def ocr_pdf_google(pdf_path):
    """
    Извлекает ПОЛНЫЙ текст из PDF с помощью Google Vision OCR.
    Исправлена проблема с обрезанием текста.
    """
    client = vision.ImageAnnotatorClient()
    
    logging.info(f"📤 Отправляю PDF в Google Vision OCR: {pdf_path}")
    
    try:
        # Читаем PDF файл
        with open(pdf_path, "rb") as pdf_file:
            content = pdf_file.read()

        # Создаем запрос для полного анализа документа
        input_config = vision.InputConfig(
            content=content,
            mime_type="application/pdf"
        )
        
        feature = vision.Feature(
            type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION
        )

        # Запрос с обработкой всех страниц
        request = vision.AnnotateFileRequest(
            input_config=input_config,
            features=[feature],
            # Убираем ограничения на страницы для полного извлечения
        )

        # Выполняем запрос
        response = client.batch_annotate_files(requests=[request])
        
        if response.responses[0].error.message:
            logging.error(f"Google Vision API ошибка: {response.responses[0].error.message}")
            return ""

        # Собираем ВЕСЬ текст со всех страниц
        full_text = ""
        page_count = 0
        
        for file_response in response.responses:
            for page_response in file_response.responses:
                page_count += 1
                if page_response.full_text_annotation:
                    page_text = page_response.full_text_annotation.text
                    if page_text:
                        full_text += page_text + "\n"
                        logging.info(f"📄 Страница {page_count}: извлечено {len(page_text)} символов")
        
        logging.info(f"✅ Google Vision OCR завершен: {len(full_text)} символов, {page_count} страниц")
        logging.info(f"📄 OCR RAW (первые 1000 символов):\n{full_text[:1000]}")
        
        return full_text.strip()
        
    except Exception as e:
        logging.error(f"❌ Ошибка Google Vision OCR: {e}")
        return ""


def ocr_pdf_google_enhanced(pdf_path):
    """
    Улучшенная версия OCR с дополнительными возможностями.
    Извлекает не только текст, но и структурную информацию.
    """
    client = vision.ImageAnnotatorClient()
    
    logging.info(f"🔍 Расширенный анализ PDF: {pdf_path}")
    
    try:
        with open(pdf_path, "rb") as pdf_file:
            content = pdf_file.read()

        input_config = vision.InputConfig(
            content=content,
            mime_type="application/pdf"
        )
        
        # Используем несколько типов анализа
        features = [
            vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION),
            vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION),
        ]

        request = vision.AnnotateFileRequest(
            input_config=input_config,
            features=features,
        )

        response = client.batch_annotate_files(requests=[request])
        
        result = {
            "full_text": "",
            "structured_data": [],
            "page_count": 0,
            "confidence": 0.0
        }
        
        total_confidence = 0
        confidence_count = 0
        
        for file_response in response.responses:
            for page_response in file_response.responses:
                result["page_count"] += 1
                
                # Основной текст
                if page_response.full_text_annotation:
                    page_text = page_response.full_text_annotation.text
                    if page_text:
                        result["full_text"] += page_text + "\n"
                
                # Структурированные данные
                for text_annotation in page_response.text_annotations:
                    if text_annotation.description and text_annotation.bounding_poly:
                        result["structured_data"].append({
                            "text": text_annotation.description,
                            "confidence": text_annotation.score if hasattr(text_annotation, 'score') else 1.0,
                            "bounds": {
                                "vertices": [
                                    {"x": vertex.x, "y": vertex.y} 
                                    for vertex in text_annotation.bounding_poly.vertices
                                ]
                            }
                        })
                        
                        if hasattr(text_annotation, 'score'):
                            total_confidence += text_annotation.score
                            confidence_count += 1
        
        # Вычисляем среднюю уверенность
        if confidence_count > 0:
            result["confidence"] = total_confidence / confidence_count
        
        result["full_text"] = result["full_text"].strip()
        
        logging.info(f"✅ Расширенный OCR: {len(result['full_text'])} символов, "
                    f"{len(result['structured_data'])} элементов, "
                    f"уверенность: {result['confidence']:.2f}")
        
        return result
        
    except Exception as e:
        logging.error(f"❌ Ошибка расширенного OCR: {e}")
        return {
            "full_text": "",
            "structured_data": [],
            "page_count": 0,
            "confidence": 0.0
        }