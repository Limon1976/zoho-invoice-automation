

from dataclasses import dataclass
from typing import Optional

@dataclass
class Supplier:
    name: Optional[str] = None
    vat: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    tax_id: Optional[str] = None
    email: Optional[str] = None

@dataclass
class Proforma:
    vin: str
    cost_price: float
    supplier: Supplier
    car_model: str
    car_item_name: str
    is_valid_for_us: bool
    our_company: str
    tax_rate: str
    currency: str
    payment_terms: Optional[str] = None

@dataclass
class Invoice:
    bill_number: str
    supplier: Supplier
    date: str
    currency: str
    total_amount: float
    item_details: str
    account: str
    our_company: str

@dataclass
class Contract:
    bill_number: str
    supplier: Supplier
    date: str
    currency: str
    total_amount: float
    item_details: str
    account: str
    our_company: str
    # Поля специфичные для контрактов
    vin: str = ""
    car_model: str = ""
    car_item_name: str = ""
    contract_type: str = "purchase"  # purchase, lease, etc.
    delivery_date: str = ""
    payment_terms: str = ""

def supplier_from_dict(data):
    return Supplier(
        name=data.get("name"),
        vat=data.get("vat"),
        address=data.get("address"),
        phone=data.get("phone"),
        country=data.get("country"),
        tax_id=data.get("tax_id"),
        email=data.get("email"),
    )

def proforma_from_dict(data):
    supplier = supplier_from_dict(data.get("supplier", {}))
    return Proforma(
        vin=data["vin"],
        cost_price=data["cost_price"],
        supplier=supplier,
        car_model=data["car_model"],
        car_item_name=data["car_item_name"],
        is_valid_for_us=data["is_valid_for_us"],
        our_company=data["our_company"],
        tax_rate=data["tax_rate"],
        currency=data["currency"],
        payment_terms=data.get("payment_terms")
    )

def invoice_from_dict(data):
    supplier = supplier_from_dict(data.get("supplier", {}))
    return Invoice(
        bill_number=data["bill_number"],
        supplier=supplier,
        date=data["date"],
        currency=data["currency"],
        total_amount=data["total_amount"],
        item_details=data["item_details"],
        account=data["account"],
        our_company=data["our_company"]
    )