from functions.assistant_logic import zoho_create_quote
from functions.assistant_logic import is_outgoing_invoice, is_auto_proforma
import logging
logger = logging.getLogger(__name__)

import os
import json
from functions.agent_invoice_parser import analyze_proforma_via_agent
from telegram import Update
from telegram.ext import ContextTypes

INBOX_FOLDER = "inbox"
os.makedirs(INBOX_FOLDER, exist_ok=True)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message is None or message.document is None:
        if message:
            await message.reply_text("❌ Не найден документ в сообщении. Пожалуйста, отправьте PDF-файл.")
        return

    document = message.document
    if document.mime_type != "application/pdf":
        await message.reply_text("❌ Пожалуйста, отправьте PDF-файл.")
        return

    if not document.file_name:
        await message.reply_text("❌ Не удалось определить имя файла. Пожалуйста, переименуйте файл и попробуйте снова.")
        return

    file = await document.get_file()
    file_path = os.path.join(INBOX_FOLDER, document.file_name)
    await file.download_to_drive(file_path)

    await message.reply_text(
        f"✅ Документ получен и сохранён как: {document.file_name}\n"
        f"⏳ Обрабатываем..."
    )

    try:
        result = analyze_proforma_via_agent(file_path)

        # --- Проверка на наличие VAT вашей компании ---
        our_vats = ["EE102288270", "PL5272956146"]  # Дублирует список из agent_invoice_parser.py
        vat_found = False
        for vat in our_vats:
            if vat in str(result):
                vat_found = True
                break
        if not vat_found:
            await message.reply_text("❗️ Внимание: VAT вашей компании не найден в документе!")

        # --- Проверка на исходящий счет (наша компания как supplier) ---
        from functions.assistant_logic import is_outgoing_invoice, is_auto_proforma, zoho_create_quote
        if is_outgoing_invoice(result):
            await message.reply_text("🛑 Обнаружен исходящий счет — обработка пропущена.")
            return

        # --- Если это входящая проформа на авто — создаем Quote в Zoho ---
        if is_auto_proforma(result):
            zoho_create_quote(result)
            await message.reply_text("🚗 Создан quote в Zoho Books для автомобиля!")

        try:
            result_json = json.dumps(result, indent=2, ensure_ascii=False)
        except Exception as json_err:
            logger.error(f"❌ Ошибка при сериализации результата: {json_err}")
            logger.error(f"📦 Исходный результат: {result}")
            await message.reply_text("❌ Ошибка при форматировании результата.")
            return

        await message.reply_text(
            f"📄 Результат анализа документа:\n<pre>{result_json}</pre>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.exception(f"Ошибка при анализе документа: {e}")
        await message.reply_text("❌ Произошла ошибка при анализе. Подробности записаны в журнал.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message is None or not message.photo:
        if message:
            await message.reply_text("❌ Не найдено фото в сообщении. Пожалуйста, отправьте изображение.")
        return
    photo = message.photo[-1]
    file = await photo.get_file()
    file_path = os.path.join(INBOX_FOLDER, f"photo_{photo.file_id}.jpg")
    await file.download_to_drive(file_path)
    await message.reply_text("📷 Фото проформы получено. Обработка VIN будет позже.")