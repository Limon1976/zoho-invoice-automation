# Zoho Invoice Automation

[🇺🇸 English](README.md) | [🇷🇺 Русская версия](README_RU.md)

Automated invoice and proforma processing system with Zoho Books integration using OCR and AI analysis.

## 🚀 Project Overview

This project automates document processing (invoices, proformas, receipts) using:
- **OCR text recognition** from PDF documents (Google Vision API)
- **AI document analysis** (OpenAI GPT-4)
- **Automatic integration** with Zoho Books API
- **Telegram bot** for notifications and management

## ✨ Key Features

### 📄 Document Processing
- Automatic text recognition from PDF files
- Structured data extraction (supplier, amount, date, VAT)
- Document type identification (invoice, proforma, return)
- Purchase type classification (vehicles vs services)

### 🏢 Company Management
- **Automatic document ownership detection**
- **Fallback logic**: VAT number priority, company name as backup
- **Intelligent company name matching**
- **Automatic country prefix addition** to VAT numbers

### 🚗 Automotive Industry Specialization
- VIN number recognition
- Vehicle purchase vs service distinction
- Car details extraction (model, color, mileage)
- Proper handling of full price vs down payment

### 🌍 Multi-country Support
- Automatic country detection by indirect signs
- Support for various VAT formats
- Multi-language document processing (Polish, English, Estonian, Swedish)

## 🛠 Technologies

- **Python 3.11+**
- **OpenAI GPT-4** - document analysis
- **Google Vision API** - OCR recognition
- **Zoho Books API** - accounting system integration
- **Telegram Bot API** - notifications
- **FastAPI** - web server
- **PDFPlumber/PyMuPDF** - PDF processing

## 📋 Requirements

```bash
# Main dependencies
openai>=1.30.1
google-cloud-vision>=3.10.2
python-telegram-bot>=20.7
fastapi>=0.115.14
pdfplumber>=0.11.7
pymupdf>=1.26.1
```

## 🔧 Installation

1. **Clone the repository:**
```bash
git clone https://github.com/Limon1976/zoho-invoice-automation.git
cd zoho-invoice-automation
```

2. **Create virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables:**
```bash
# Create .env file
OPENAI_API_KEY=your_openai_api_key
OPENAI_ASSISTANT_ID=your_assistant_id
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
TELEGRAM_BOT_TOKEN=your_telegram_token
ZOHO_CLIENT_ID=your_zoho_client_id
ZOHO_CLIENT_SECRET=your_zoho_secret
```

5. **Configure settings:**
```python
# config.py
OUR_COMPANIES = [
    {
        "name": "Your Company Name",
        "vat": "PL1234567890",
        "country": "Poland"
    }
]
```

## 🚀 Usage

### Run all services
```bash
python run_all.py
```

### Run individual components

**Telegram bot:**
```bash
python telegram_bot/bot_main.py
```

**MCP connector:**
```bash
python mcp_connector/mcp_main.py
```

**Folder monitoring:**
```bash
python watcher/monitor.py
```

### Process single document
```python
from functions.agent_invoice_parser import analyze_proforma_via_agent

result = analyze_proforma_via_agent('path/to/document.pdf')
print(result)
```

## 📁 Project Structure

```
├── functions/              # Core processing logic
│   ├── agent_invoice_parser.py  # AI document analysis
│   ├── assistant_logic.py       # OpenAI Assistant logic
│   └── zoho_api.py             # Zoho integration
├── telegram_bot/          # Telegram bot
├── mcp_connector/          # MCP connector
├── watcher/               # File monitoring
├── inbox/                 # Incoming documents
├── invoices/              # Processed documents
└── keys/                  # API keys (not in git)
```

## 🔍 Usage Examples

### Invoice Processing
```python
# Automatic PDF processing
result = analyze_proforma_via_agent('invoice.pdf')

# Result contains:
{
    "document_type": "invoice",
    "supplier": {
        "name": "Company Name",
        "vat": "PL1234567890",
        "address": "Address"
    },
    "our_company": {
        "name": "Our Company",
        "vat": "PL0987654321"
    },
    "total_amount": 1000.0,
    "currency": "PLN",
    "date": "2024-01-15",
    "account": "Office Expenses"
}
```

### VAT Fallback Logic
- **Priority**: VAT number determines document ownership
- **Fallback**: If VAT is missing, use company name
- **Security**: Incorrect VAT = document rejection

## 🎯 Features

### Intelligent Company Recognition
- Automatic name matching with variations
- Handling of abbreviations and full names
- Country prefix addition to VAT numbers

### Specialized Vehicle Processing
- Purchase vs service distinction for vehicles
- VIN and vehicle details extraction
- Correct pricing handling

### Monitoring and Notifications
- Telegram notifications for new documents
- Comprehensive operation logging
- Processing status tracking

## 🔒 Security

- All API keys stored in environment variables
- Key files excluded from git
- Logging contains no sensitive data

## 🤝 Project Development

### Planned Improvements
- [ ] Web interface for monitoring
- [ ] Additional document format support
- [ ] Enhanced analytics
- [ ] External integration APIs

### Contributing
1. Fork the project
2. Create a feature branch
3. Make your changes
4. Create a Pull Request

## 📄 License

This project uses [MIT License](LICENSE).

## 📞 Support

For questions and suggestions, create [Issues](https://github.com/Limon1976/zoho-invoice-automation/issues) in the repository.

---

**Made with ❤️ for business process automation** 