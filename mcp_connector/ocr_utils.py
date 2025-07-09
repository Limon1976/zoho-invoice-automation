

from google.cloud import vision
from google.cloud.vision_v1 import types

def ocr_pdf_google(pdf_path):
    """
    Извлекает текст из PDF с помощью Google Vision OCR (распознаёт ВСЕ страницы).
    """
    client = vision.ImageAnnotatorClient()

    with open(pdf_path, "rb") as pdf_file:
        content = pdf_file.read()

    input_config = types.InputConfig(
        content=content,
        mime_type="application/pdf"
    )
    feature = types.Feature(
        type=vision.Feature.Type.DOCUMENT_TEXT_DETECTION
    )

    request = types.AnnotateFileRequest(
        input_config=input_config,
        features=[feature]
        # Все страницы, параметр pages не указываем!
    )

    response = client.batch_annotate_files(requests=[request])

    full_text = ""
    for resp in response.responses:
        for annotation in resp.responses:
            if annotation.full_text_annotation.text:
                full_text += annotation.full_text_annotation.text + "\n"
    return full_text.strip()