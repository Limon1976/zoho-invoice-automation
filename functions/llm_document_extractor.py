from __future__ import annotations

import os
import json
import logging
from typing import Dict, Any, Optional

try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore

logger = logging.getLogger(__name__)


def _get_client() -> Optional[Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not OpenAI or not api_key:
        logger.warning("OpenAI client unavailable: missing SDK or OPENAI_API_KEY")
        return None
    return OpenAI(api_key=api_key)


_EXTRACT_SYSTEM = (
    "You are a precise information extractor for invoices, proformas, purchase orders, and contracts. "
    "Output a compact JSON following the schema. Never include prose outside JSON."
)

_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "supplier_name": {"type": "string"},
        "supplier_address": {"type": "string"},
        "supplier_country": {"type": "string"},
        "supplier_phone": {"type": "string"},
        "supplier_email": {"type": "string"},
        "vat": {"type": "string"},
        "document_type": {"type": "string", "description": "one of: contract_sale, proforma_invoice, invoice, service_invoice, delivery_note"},
        "bill_number": {"type": "string"},
        "date": {"type": "string"},
        "vin": {"type": "string"},
        "total_amount": {"type": "number", "description": "Prefer NET amount (pre-tax)."},
        "net_amount": {"type": "number", "description": "Net amount (pre-tax)"},
        "vat_amount": {"type": "number", "description": "Tax/VAT amount"},
        "gross_amount": {"type": "number", "description": "Gross/total with tax"},
        "currency": {"type": "string"},
        "tax_rate": {"type": "number"},
        "notes": {"type": "string"},
        # Parties: explicitly extract seller (issuer) and buyer (our company usually)
        "seller_name": {"type": "string", "description": "Seller company name (issuer of document)"},
        "seller_vat": {"type": "string"},
        "buyer_name": {"type": "string", "description": "Buyer company name (customer)"},
        "buyer_vat": {"type": "string"},
        # Backward compatible issuer fields (filled from seller_*):
        "issuer_name": {"type": "string", "description": "alias of seller_name"},
        "issuer_address": {"type": "string"},
        "issuer_vat": {"type": "string"},
        "contact_person": {"type": "string"},
        "issuer_contact_person": {"type": "string"},
        "car_brand": {"type": "string"},
        "car_model": {"type": "string"},
        "car_year": {"type": "string"},
        "item_description": {"type": "string", "description": "Concise English description of the car including notable features if present"},
        "service_description": {"type": "string", "description": "If this is a service invoice, short description of the service (in English)"},
        "issue_date": {"type": "string", "description": "The document issue date if explicitly present"},
        "due_date": {"type": "string", "description": "The due date/payment due if explicitly present"},
        "car_features": {"type": "array", "items": {"type": "string"}},
        "product_category": {"type": "string", "description": "One of: FLOWERS, CARS, SERVICES, UTILITIES, FOOD, OTHER"},
        "detected_flower_names": {"type": "array", "items": {"type": "string"}},
        # Structured supplier address to avoid city/zip mixing
        "supplier_address_struct": {
            "type": "object",
            "properties": {
                "street": {"type": "string"},
                "city": {"type": "string"},
                "zip": {"type": "string"},
                "country": {"type": "string"}
            }
        },
        "bank": {
            "type": "object",
            "properties": {
                "bank_name": {"type": "string"},
                "bank_address": {"type": "string"},
                "bank_account": {"type": "string"},
                "iban": {"type": "string"},
                "swift": {"type": "string"},
                "payment_method": {"type": "string"},
                "payment_due_date": {"type": "string"}
            }
        }
    },
    "required": ["supplier_name"]
}


def llm_extract_fields(ocr_text: str) -> Dict[str, Any]:
    """Extract structured fields from OCR text using GPT-4. Returns empty dict on failure."""
    client = _get_client()
    if not client or not ocr_text:
        return {}
    try:
        prompt = (
            "Extract fields as JSON strictly following this JSON Schema."
            " Critical rules:"
            " 1) issuer = seller; buyer is our company/customer."
            " 2) Never set issuer/seller to our companies: 'TaVie Europe OÜ', 'PARKENTERTAINMENT', VATs 'EE102288270', 'PL5272956146'. If buyer matches these, keep seller as the other party."
            " 3) Fill issuer_name/issuer_vat from seller_name/seller_vat for backward compatibility."
            " 4) Prefer NET amounts for 'total_amount'. If only gross and VAT are present, set net_amount = gross_amount - vat_amount;"
            " if only gross and tax_rate are present, estimate net_amount = round(gross_amount / (1 + tax_rate/100), 2)."
            " 5) Produce supplier_address_struct (street, city, zip, country) if possible to avoid mixing city/zip into address lines.\n\n"
            f"{json.dumps(_EXTRACT_SCHEMA)}\n\n"
            "Text:\n" + ocr_text[:16000]
        )
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_GPT4_MODEL", "gpt-4o"),
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM + " Also classify product_category. If the items are cut flowers/flower goods, set product_category=FLOWERS and list detected_flower_names (e.g., rose, tulip, gypsophila, ruscus, alstroemeria, chrysanthemum; use Latin/English/Polish names). If it's a service invoice, fill service_description in clear English including the billing period (e.g., 'Basic monthly subscription for August 2025' or 'IT services for July-August 2025'). If dates like 'Date of issue' or 'Due date' exist, set issue_date and due_date respectively."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        
        # DEBUG: Log extracted fields for troubleshooting
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔍 LLM extracted fields: {list(data.keys())}")
        if data.get('service_description'):
            logger.info(f"🔍 service_description: {data['service_description']}")
        if data.get('issue_date'):
            logger.info(f"🔍 issue_date: {data['issue_date']}")
        if data.get('due_date'):
            logger.info(f"🔍 due_date: {data['due_date']}")
        if data.get('product_category'):
            logger.info(f"🔍 product_category: {data['product_category']}")
        if data.get('detected_flower_names'):
            logger.info(f"🔍 detected_flower_names: {data['detected_flower_names']}")
        
        # minimal cleanup and normalization
        if data.get("vat"):
            data["vat"] = str(data["vat"]).replace(" ", "").upper()
        # ensure numeric fields are numbers
        for k in ["net_amount", "vat_amount", "gross_amount", "total_amount", "tax_rate"]:
            if k in data and isinstance(data[k], str):
                try:
                    data[k] = float(data[k].replace(",", "."))
                except Exception:
                    pass
        # derive net if missing
        net = data.get("net_amount")
        gross = data.get("gross_amount")
        vat = data.get("vat_amount")
        rate = data.get("tax_rate")
        if net is None:
            if isinstance(gross, (int, float)) and isinstance(vat, (int, float)):
                net = round(float(gross) - float(vat), 2)
            elif isinstance(gross, (int, float)) and isinstance(rate, (int, float)) and rate > 0:
                net = round(float(gross) / (1.0 + float(rate) / 100.0), 2)
        if net is not None:
            data["net_amount"] = net
            data.setdefault("total_amount", net)
        # Map seller_* to issuer_*
        if data.get("seller_name") and not data.get("issuer_name"):
            data["issuer_name"] = data.get("seller_name")
        if data.get("seller_vat") and not data.get("issuer_vat"):
            data["issuer_vat"] = data.get("seller_vat")
        # Flatten structured supplier address
        saddr = data.get("supplier_address_struct") or {}
        if isinstance(saddr, dict):
            if saddr.get("street"):
                data["supplier_street"] = saddr.get("street")
            if saddr.get("city"):
                data["supplier_city"] = saddr.get("city")
            if saddr.get("zip"):
                data["supplier_zip_code"] = saddr.get("zip")
            if saddr.get("country"):
                data["supplier_country"] = data.get("supplier_country") or saddr.get("country")
        return data
    except Exception as e:
        logger.warning(f"LLM extract failed: {e}")
        return {}


_RISK_SYSTEM = (
    "You are a contract risk analyst for a small trading company. "
    "Identify risks and obligations for the buyer, summarize payment, delivery, warranty, taxes, jurisdiction, penalties, cancellation, liability, and any unusual clauses. "
    "Output concise JSON with fields: risks[list[str]], obligations[list[str]], jurisdiction[str], payment_terms[str], delivery_terms[str], warranty[str], taxes[str], penalties[str], cancellation[str], unusual[str]."
)


def llm_analyze_contract_risks(ocr_text: str) -> Dict[str, Any]:
    client = _get_client()
    if not client or not ocr_text:
        return {}
    try:
        prompt = "Analyze this contract text for risks and obligations. Return JSON only.\n" + ocr_text[:16000]
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_GPT4_MODEL", "gpt-4o"),
            messages=[
                {"role": "system", "content": _RISK_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)
    except Exception as e:
        logger.warning(f"LLM risk analyze failed: {e}")
        return {}


def llm_translate_to_en(text: str) -> str:
    """Translate arbitrary text to English concisely using LLM. Return original on failure."""
    client = _get_client()
    if not client or not text:
        return text
    try:
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_GPT4_MODEL", "gpt-4o"),
            messages=[
                {"role": "system", "content": "Translate the user's text to English. Preserve bullets, numbers and keep it concise. Output plain text only."},
                {"role": "user", "content": text[:16000]},
            ],
            temperature=0.1,
        )
        content = resp.choices[0].message.content or text
        return content
    except Exception as e:
        logger.warning(f"LLM translate EN failed: {e}")
        return text


def llm_generate_car_description_en(ocr_text: str, brand: str, model: str, vin: str) -> str:
    """Generate a single‑paragraph English car description from OCR with key specs and notable clauses."""
    client = _get_client()
    base_title = f"{(brand or '').strip()} {(model or '').strip()}".strip()
    if not client or not ocr_text:
        # Minimal fallback
        parts = [p for p in [base_title, f"VIN {vin}" if vin else None] if p]
        return ". ".join(parts) if parts else (vin or base_title or "Car")
    try:
        sys_prompt = (
            "You write concise product descriptions for vehicles in English."
            " Extract from the text: color, mileage, gearbox, power, first registration/date, any notable conditions (e.g., no warranty/as-is, export, deposit)."
            " Output a single sentence (max 35 words), no headings, no lists."
        )
        user_prompt = (
            f"Context: {base_title} VIN {vin}.\n"
            "Compose an English one-sentence description with key specs and notable conditions for catalog (Zoho Item).\n"
            "Text:\n" + ocr_text[:16000]
        )
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_GPT4_MODEL", "gpt-4o"),
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        desc = (resp.choices[0].message.content or "").strip()
        # Ensure English
        desc = llm_translate_to_en(desc)
        return desc
    except Exception as e:
        logger.warning(f"LLM car description failed: {e}")
        parts = [p for p in [base_title, f"VIN {vin}" if vin else None] if p]
        return ". ".join(parts) if parts else (vin or base_title or "Car")


def llm_translate_to_ru(text: str) -> str:
    """Translate arbitrary text to Russian concisely using LLM. Return original on failure."""
    client = _get_client()
    if not client or not text:
        return text
    try:
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_GPT4_MODEL", "gpt-4o"),
            messages=[
                {"role": "system", "content": "Translate the user's text to Russian. Preserve bullets and concise style. Output plain text only."},
                {"role": "user", "content": text[:16000]},
            ],
            temperature=0.1,
        )
        content = resp.choices[0].message.content or text
        return content
    except Exception as e:
        logger.warning(f"LLM translate failed: {e}")
        return text


def llm_select_account(account_names: list[str], context_text: str, supplier_name: str = "", category: str = "") -> Dict[str, Any]:
    """Ask LLM to pick the best expense account from a provided list. Returns {name, confidence}.
    If LLM unavailable, returns {}.
    """
    client = _get_client()
    if not client or not account_names:
        return {}
    try:
        schema = {"type": "object", "properties": {"name": {"type": "string"}, "confidence": {"type": "number"}}}
        prompt = (
            "Choose the best matching expense account name from this list based on the document context. "
            "Return JSON with fields: name (must be EXACTLY one of the provided items) and confidence (0..1).\n\n"
            "Guidelines:\n"
            "- Software/SaaS/platform subscriptions (SuperCMR, web platforms, IT tools) → 'IT and Internet Expenses' or 'Subscriptions'\n"
            "- Professional consulting services → 'Consultant Expense'\n"
            "- Legal services → 'Lawyers'\n"
            "- Utilities/telecom → 'Utility Expenses' or 'Telephone Expense'\n"
            "- Flowers/floriculture → 'Flowers'\n"
            "- Courier/postal/shipping/delivery services (NOVA POST, DHL, UPS, FedEx) → 'Delivery' or 'Shipping Charge'\n\n"
            f"Accounts: {account_names}\n"
            f"Supplier: {supplier_name}\n"
            f"Category hint: {category}\n"
            "Context (text):\n" + (context_text or "")[:8000]
        )
        
        # DEBUG: Log what we're sending to LLM
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🔍 llm_select_account input: {len(account_names)} accounts: {account_names[:5]}...")
        logger.info(f"🔍 Full account list: {account_names}")
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_GPT4_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You are a careful accounting classifier. Always answer with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        logger.info(f"🔍 llm_select_account result: {data}")
        if isinstance(data.get("name"), str) and data["name"] in account_names:
            try:
                data["confidence"] = float(data.get("confidence", 0))
            except Exception:
                data["confidence"] = 0.0
            return data
        return {}
    except Exception as e:
        logger.warning(f"LLM select account failed: {e}")
        return {}
