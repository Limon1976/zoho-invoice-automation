"""
Zoho VAT Update Tester
======================

Запуск:
  source venv/bin/activate
  python -m src.scripts.zoho_vat_tester --org 20082562863 --name "HIBISPOL SP. Z.O.O." --vat PL1182241766
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any, Dict, Optional, List

from src.infrastructure.config import config
from src.infrastructure.zoho_api import ZohoAPIClient


logger = logging.getLogger("zoho_vat_tester")
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


async def ensure_client() -> ZohoAPIClient:
    z = config.zoho
    missing = [k for k, v in {
        "ZOHO_CLIENT_ID": z.client_id,
        "ZOHO_CLIENT_SECRET": z.client_secret,
        "ZOHO_REFRESH_TOKEN": z.refresh_token,
    }.items() if not v]
    if missing:
        raise RuntimeError(f"Отсутствуют переменные окружения: {', '.join(missing)}")
    return ZohoAPIClient(z.client_id, z.client_secret, z.refresh_token or "")


def normalize_vat(v: str) -> str:
    return (v or "").replace(" ", "").replace("-", "").upper()


async def get_contact_id_by_name(client: ZohoAPIClient, org_id: str, name_contains: str) -> Optional[str]:
    logger.info(f"Ищу контакт по имени contains='{name_contains}' (vendor)...")
    # 1) Поиск с типом vendor
    resp = await client.search_contacts(
        organization_id=org_id,
        contact_type="vendor",
        contact_name_contains=name_contains,
        per_page=200,
    )
    logger.info(f"Ответ поиска (vendor, укороченный): {json.dumps({k: v for k, v in (resp or {}).items() if k != 'contacts'}, ensure_ascii=False)}")
    contacts = (resp or {}).get("contacts") or []
    for c in contacts:
        if name_contains.lower() in (c.get("contact_name") or "").lower():
            logger.info(f"Найден контакт: {c.get('contact_name')} -> contact_id={c.get('contact_id')}")
            return c.get("contact_id")

    # 2) Без фильтра по типу
    logger.info("Повторный поиск без contact_type...")
    resp = await client.search_contacts(
        organization_id=org_id,
        contact_name_contains=name_contains,
        per_page=200,
    )
    logger.info(f"Ответ поиска (all types, укороченный): {json.dumps({k: v for k, v in (resp or {}).items() if k != 'contacts'}, ensure_ascii=False)}")
    contacts = (resp or {}).get("contacts") or []
    for c in contacts:
        if name_contains.lower() in (c.get("contact_name") or "").lower():
            logger.info(f"Найден контакт: {c.get('contact_name')} -> contact_id={c.get('contact_id')}")
            return c.get("contact_id")

    # 3) Грубая стратегия: пролистать первые 5 страниц и искать подстроку локально
    logger.info("Листаю список контактов (до 5 страниц) и ищу подстроку локально...")
    for page in range(1, 6):
        lst = await client.get_contacts(organization_id=org_id, page=page, per_page=200)
        clist = (lst or {}).get("contacts") or []
        for c in clist:
            if name_contains.lower() in (c.get("contact_name") or "").lower():
                logger.info(f"Найден (листинг p{page}): {c.get('contact_name')} -> contact_id={c.get('contact_id')}")
                return c.get("contact_id")
        page_context = (lst or {}).get("page_context") or {}
        if not page_context.get("has_more_page"):
            break

    logger.warning("Контакт не найден")
    return None


async def read_custom_fields(client: ZohoAPIClient, org_id: str) -> Dict[str, Any]:
    logger.info("Читаю метаданные кастомных полей (contacts)...")
    meta = await client.get_contact_custom_fields(org_id)
    logger.info(f"customfields keys: {list((meta or {}).keys())}")
    logger.info(f"customfields raw (укорочено до 1000 симв.): {json.dumps(meta, ensure_ascii=False)[:1000]}")
    return meta or {}


def find_tax_field_index(meta: Dict[str, Any]) -> Optional[int]:
    cf = (meta or {}).get("customfields")
    # customfields может быть списком или словарём с ключом 'contact'
    if isinstance(cf, dict):
        fields = cf.get("contact") or []
    else:
        fields = cf or []

    for f in fields:
        if not isinstance(f, dict):
            continue
        label = (f.get("label") or "").lower()
        api_name = (f.get("api_name") or f.get("placeholder") or "").lower()
        if any(x in label for x in ["tax", "vat", "ид", "инн", "nip", "tax id"]) or api_name in {"cf_tax_id", "tax_id", "vat"}:
            try:
                return int(f.get("index")) if f.get("index") is not None else None
            except Exception:
                return None
    return None


async def try_update_variants(client: ZohoAPIClient, org_id: str, contact_id: str, vat_value: str, tax_index: Optional[int]) -> None:
    variants = []
    if tax_index is not None:
        variants.append({"custom_fields": [{"index": int(tax_index), "value": vat_value}]})
    variants.append({"tax_id": vat_value})

    for i, payload in enumerate(variants, 1):
        logger.info(f"Пробую обновление (вариант {i}): {json.dumps(payload, ensure_ascii=False)}")
        resp = await client.update_contact(contact_id=contact_id, contact_data=payload, organization_id=org_id)
        if resp is not None:
            logger.info(f"Успех (вариант {i}): {json.dumps(resp, ensure_ascii=False)}")
        else:
            logger.error(f"Ошибка (вариант {i}). См. логи HTTP выше")


async def find_contact_by_listing(
    client: ZohoAPIClient,
    org_id: str,
    name_contains: Optional[str],
    vat_candidates: List[str],
) -> Optional[str]:
    page = 1
    per_page = 200
    candidates_norm = [normalize_vat(v) for v in vat_candidates if v]
    while True:
        lst = await client.get_contacts(organization_id=org_id, page=page, per_page=per_page)
        contacts = (lst or {}).get("contacts") or []
        if not contacts:
            break

        # Получим детали, чтобы видеть tax_id/custom_fields
        for c in contacts:
            cid = c.get("contact_id")
            if not cid:
                continue
            details = await client.get_contact_details(org_id, cid) or {}
            cname = (details.get("contact_name") or c.get("contact_name") or "")
            tax_id_val = normalize_vat(details.get("tax_id") or "")
            cf_list = details.get("custom_fields") or []
            cf_vals = [normalize_vat(cf.get("value") or "") for cf in cf_list]

            name_ok = True
            if name_contains:
                name_ok = name_contains.lower() in cname.lower()

            vat_ok = False
            for token in candidates_norm:
                if not token:
                    continue
                if token == tax_id_val or token in cf_vals:
                    vat_ok = True
                    break

            if name_ok or vat_ok:
                logger.info(f"Найден по листингу: {cname} (tax_id={details.get('tax_id')}) -> {cid}")
                return cid

        page_context = (lst or {}).get("page_context") or {}
        if not page_context.get("has_more_page"):
            break
        page += 1
    return None


async def main() -> None:
    parser = argparse.ArgumentParser(description="Zoho Books VAT updater tester")
    parser.add_argument("--org", required=False, default=config.zoho.organization_id, help="Organization ID")
    parser.add_argument("--name", required=True, help="Substring of contact name to search")
    parser.add_argument("--vat", required=True, help="VAT value to set (with country prefix)")
    parser.add_argument("--vat-search", required=False, help="VAT value to search contact by (if differs from --vat)")
    args = parser.parse_args()

    org_id = args.org or config.zoho.organization_id
    if not org_id:
        raise RuntimeError("Не указан organization_id (передайте --org или задайте ZOHO_ORGANIZATION_ID в .env)")

    client = await ensure_client()
    try:
        contact_id = await get_contact_id_by_name(client, org_id, args.name)
        if not contact_id:
            # Пробуем найти по VAT среди листинга
            search_tokens = [args.vat, (args.vat_search or ""), normalize_vat(args.vat), normalize_vat(args.vat_search or "")]
            contact_id = await find_contact_by_listing(client, org_id, args.name, search_tokens)
            if not contact_id:
                logger.error("Прерывание: contact_id не найден (по имени и VAT)")
                return

        meta = await read_custom_fields(client, org_id)
        tax_index = find_tax_field_index(meta)
        logger.info(f"Определен индекс TAX/VAT поля: {tax_index}")

        await try_update_variants(client, org_id, contact_id, args.vat, tax_index)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())


