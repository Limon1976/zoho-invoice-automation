import asyncio, json
from config.zoho_auth import get_zoho_credentials
from src.infrastructure.zoho_api import ZohoAPIClient
from functions.zoho_api import get_contact_by_name

org_id='20082562863'
name='HIBISPOL SP. Z.O.O.'
creds=get_zoho_credentials()
print('CREDS OK:', bool(creds))
contact = get_contact_by_name(name, org_id)
print('CONTACT:', (contact or {}).get('contact_id'), (contact or {}).get('contact_name'))

async def main():
    client = ZohoAPIClient(creds['client_id'], creds['client_secret'], creds['refresh_token'])
    try:
        if not contact or not contact.get('contact_id'):
            print('ERR: contact not found'); return
        cid = contact['contact_id']
        url = f'https://www.zohoapis.eu/books/v3/contacts/{cid}?organization_id={org_id}'
        payload_api = {custom_fields:[{api_name:cf_tax_id,value:PL1182241766}]}
        print('PUT api_name:', url, payload_api)
        r1 = await client._make_request('PUT', url, json=payload_api)
        print('RESP1:', json.dumps(r1, ensure_ascii=False))
        if not r1 or (isinstance(r1, dict) and r1.get('code')!=0 and 'contact' not in r1):
            payload_tax = {tax_id:PL1182241766}
            print('PUT tax_id:', url, payload_tax)
            r2 = await client._make_request('PUT', url, json=payload_tax)
            print('RESP2:', json.dumps(r2, ensure_ascii=False))
    finally:
        await client.close()

asyncio.run(main())
