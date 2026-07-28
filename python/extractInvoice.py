import sys
import json
import base64
import pymupdf
import re

payload = json.loads(sys.stdin.read())
pdf_base64 = payload.get("data", "")

pdf_bytes = base64.b64decode(pdf_base64)
doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

text = ""
for page in doc:
    text += page.get_text()

lines = [l.strip() for l in text.split("\n") if l.strip()]

# --- Invoice Number ---
invoice_number = None
for line in lines:
    # matches INV-XXXXXX or pure numeric like 5611344371
    match = re.search(r'(?:Invoice number[:\s]*)?([A-Z]{0,4}-?\d{6,})', line)
    if match:
        invoice_number = match.group(1)
        break

# --- Date ---
date = None
date_patterns = [
    r'\b(\d{4}-\d{2}-\d{2})\b',           # 2026-06-30
    r'\b([A-Z][a-z]+ \d{1,2},? \d{4})\b', # Jun 30, 2026
    r'\b(\d{1,2}[./]\d{1,2}[./]\d{4})\b'  # 30.06.2026
]
for line in lines:
    for pattern in date_patterns:
        match = re.search(pattern, line)
        if match:
            date = match.group(1)
            break
    if date:
        break

# --- Total ---
total = None
currency = None
currency_map = {'€': 'EUR', '$': 'USD', '£': 'GBP', 'CHF': 'CHF'}

total_keywords = ['total in eur', 'total', 'gesamt', 'gesamtbetrag']
for i, line in enumerate(lines):
    if any(kw in line.lower() for kw in total_keywords):
        # look for amount in same line or next line
        search_text = line + ' ' + (lines[i+1] if i+1 < len(lines) else '')
        amount_match = re.search(r'([€$£]|CHF)\s*([\d,]+\.?\d*)', search_text)
        if not amount_match:
            amount_match = re.search(r'([\d,]+\.?\d*)\s*([€$£]|EUR|USD|GBP|CHF)', search_text)
        if amount_match:
            groups = amount_match.groups()
            for g in groups:
                if g in currency_map:
                    currency = currency_map[g]
                elif g in ['EUR', 'USD', 'GBP']:
                    currency = g
                else:
                    try:
                        total = float(g.replace(',', ''))
                    except:
                        pass
            break

# --- Vendor ---
vendor = None
vendor_keywords = ['from', 'vendor', 'supplier', 'google', 'gmbh', 'ag', 'limited', 'ltd', 'inc']
bill_to_idx = next((i for i, l in enumerate(lines) if 'bill to' in l.lower()), None)
if bill_to_idx:
    # vendor is likely before "bill to"
    for line in lines[:bill_to_idx]:
        if any(kw in line.lower() for kw in vendor_keywords):
            vendor = line
            break

# --- Client (Bill to) ---
client_name = None
client_email = None
if bill_to_idx:
    client_name = lines[bill_to_idx + 1] if bill_to_idx + 1 < len(lines) else None
    for line in lines[bill_to_idx:bill_to_idx + 6]:
        if re.match(r'[^@]+@[^@]+\.[^@]+', line):
            client_email = line
            break

# --- Line items ---
services = []
item_keywords = ['subscription', 'service', 'leistung', 'position', 'artikel']
for i, line in enumerate(lines):
    if any(kw in line.lower() for kw in item_keywords) and i + 1 < len(lines):
        amount_match = re.search(r'([\d,]+\.?\d{2})', lines[i + 1] if i + 1 < len(lines) else '')
        if amount_match:
            services.append({
                'name': line,
                'price': float(amount_match.group(1).replace(',', ''))
            })

result = {
    'invoiceNumber': invoice_number,
    'date': date,
    'currency': currency or 'EUR',
    'vendor': vendor,
    'client': {
        'name': client_name,
        'email': client_email
    },
    'services': services,
    'total': total
}

print(json.dumps(result))