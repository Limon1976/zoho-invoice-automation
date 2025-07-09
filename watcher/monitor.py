from functions.agent_invoice_parser import analyze_proforma_via_agent
import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

INBOX_FOLDER = "inbox"

class InvoiceHandler(FileSystemEventHandler):
    def on_created(self, event):
        self._handle(event)

    def on_modified(self, event):
        self._handle(event)

    def _handle(self, event):
        if not event.is_directory and event.src_path.endswith(".pdf"):
            print(f"📥 Обнаружен файл: {event.src_path}")
            # TODO: Интеграция с анализом проформы/инвойса
            # result = analyze_proforma_via_agent(event.src_path)
            # print("🤖 Агент вернул результат:", result)
            # Здесь позже можно вызвать функцию анализа:
            # analyze_invoice(event.src_path)

def start_watching():
    observer = Observer()
    observer.schedule(InvoiceHandler(), INBOX_FOLDER, recursive=False)
    observer.start()
    print(f"👁️ Слежу за папкой '{INBOX_FOLDER}'...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start_watching()