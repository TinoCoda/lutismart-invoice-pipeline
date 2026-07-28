import sys
import json
import base64
import pymupdf
import re
from datetime import datetime

payload = json.loads(sys.stdin.read())
pdf_base64 = payload.get("data", "")
pdf_bytes = base64.b64decode(pdf_base64)
doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")

# ─── MULTILINGUAL KEYWORDS ───────────────────────────────────────────────────

INVOICE_NUMBER_KEYWORDS = [
    'invoice number', 'invoice no', 'invoice #',
    'rechnungsnummer', 'rechnungs-nr', 'belegnummer',
    'numéro de facture', 'facture n°', 'nº factura',
    'numero fattura', 'factuurnummer'
]

DATE_KEYWORDS = [
    'invoice date', 'date of invoice', 'issued',
    'rechnungsdatum', 'datum', 'ausstellungsdatum',
    'date de facture', 'date d\'émission',
    'fecha de factura', 'fecha emisión'
]

TOTAL_KEYWORDS = [
    'total', 'total amount', 'amount due', 'grand total', 'balance due',
    'total in eur', 'total in usd', 'total in chf',
    'gesamtbetrag', 'gesamt', 'rechnungsbetrag', 'zu zahlen', 'endbetrag',
    'montant total', 'total ttc', 'total ht',
    'importe total', 'total a pagar',
    'totale', 'importo totale'
]

VENDOR_KEYWORDS = [
    'from', 'vendor', 'supplier', 'issued by', 'billed by',
    'absender', 'lieferant', 'rechnungssteller', 'anbieter',
    'émetteur', 'fournisseur', 'de la part de',
    'proveedor', 'emisor'
]

BILL_TO_KEYWORDS = [
    'bill to', 'billed to', 'invoice to', 'ship to', 'sold to',
    'rechnungsempfänger', 'kunde', 'auftraggeber', 'an',
    'facturer à', 'client', 'destinataire',
    'facturar a', 'cliente'
]

SUBTOTAL_KEYWORDS = [
    'subtotal', 'sub total', 'net amount', 'net total',
    'zwischensumme', 'nettobetrag', 'netto',
    'sous-total', 'montant ht', 'hors taxes',
    'subtotal', 'base imponible'
]

VAT_KEYWORDS = [
    'vat', 'tax', 'gst', 'hst',
    'mwst', 'mehrwertsteuer', 'ust', 'umsatzsteuer',
    'tva', 'taxe',
    'iva', 'impuesto'
]

CURRENCY_MAP = {
    '€': 'EUR', '$': 'USD', '£': 'GBP',
    'eur': 'EUR', 'usd': 'USD', 'gbp': 'GBP',
    'chf': 'CHF', 'cad': 'CAD', 'aud': 'AUD'
}

# ─── DATE NORMALIZATION ───────────────────────────────────────────────────────

DATE_PATTERNS = [
    (r'\b(\d{4}-\d{2}-\d{2})\b', '%Y-%m-%d'),
    (r'\b(\d{2}/\d{2}/\d{4})\b', '%d/%m/%Y'),
    (r'\b(\d{2}\.\d{2}\.\d{4})\b', '%d.%m.%Y'),
    (r'\b(\d{1,2}\s+\w+\s+\d{4})\b', None),
    (r'\b([A-Z][a-z]{2,8}\.?\s+\d{1,2},?\s+\d{4})\b', None),
    (r'\b(\d{1,2}\s+[A-Z][a-z]{2,8}\.?\s+\d{4})\b', None),
]

MONTH_MAP = {
    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
    'may': '05', 'mai': '05', 'jun': '06', 'jul': '07',
    'aug': '08', 'sep': '09', 'oct': '10', 'okt': '10',
    'nov': '11', 'dec': '12', 'dez': '12',
    'january': '01', 'february': '02', 'march': '03', 'april': '04',
    'june': '06', 'july': '07', 'august': '08', 'september': '09',
    'october': '10', 'november': '11', 'december': '12',
    'januar': '01', 'februar': '02', 'märz': '03', 'mai': '05',
    'juni': '06', 'juli': '07', 'oktober': '10', 'dezember': '12',
    'janvier': '01', 'février': '02', 'mars': '03', 'avril': '04',
    'juin': '06', 'juillet': '07', 'août': '08', 'septembre': '09',
    'octobre': '10', 'novembre': '11', 'décembre': '12'
}

def normalize_date(raw):
    if not raw:
        return None
    raw = raw.strip().rstrip(',').strip()
    # already ISO
    if re.match(r'\d{4}-\d{2}-\d{2}', raw):
        return raw
    # try numeric formats
    for fmt in ['%d/%m/%Y', '%m/%d/%Y', '%d.%m.%Y', '%Y/%m/%d']:
        try:
            return datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
        except:
            pass
    # month name formats
    lower = raw.lower()
    for month_name, month_num in MONTH_MAP.items():
        if month_name in lower:
            digits = re.findall(r'\d+', raw)
            if len(digits) >= 2:
                year = next((d for d in digits if len(d) == 4), None)
                day = next((d for d in digits if len(d) <= 2), None)
                if year and day:
                    return f"{year}-{month_num}-{day.zfill(2)}"
    return raw

# ─── AMOUNT EXTRACTION ────────────────────────────────────────────────────────

def extract_amount(text):
    text = text.replace('\u00a0', ' ')
    # €10.53 or $1,234.56
    m = re.search(r'[€$£]\s*([\d\s,]+\.?\d{0,2})', text)
    if m:
        return clean_amount(m.group(1))
    # 10.53 € or 10,53 EUR
    m = re.search(r'([\d\s,]+\.?\d{0,2})\s*(?:[€$£]|EUR|USD|GBP|CHF)', text, re.IGNORECASE)
    if m:
        return clean_amount(m.group(1))
    # plain number at end of line
    m = re.search(r'([\d]{1,3}(?:[.,\s]\d{3})*[.,]\d{2})\s*$', text.strip())
    if m:
        return clean_amount(m.group(1))
    return None

def clean_amount(raw):
    raw = raw.strip().replace(' ', '')
    # European format: 1.234,56 → 1234.56
    if re.match(r'^\d{1,3}(\.\d{3})+(,\d{2})?$', raw):
        raw = raw.replace('.', '').replace(',', '.')
    # Standard: 1,234.56 → 1234.56
    elif ',' in raw and '.' in raw:
        raw = raw.replace(',', '')
    # Only comma as decimal: 10,53 → 10.53
    elif ',' in raw and '.' not in raw:
        raw = raw.replace(',', '.')
    try:
        return float(raw)
    except:
        return None

# ─── CURRENCY DETECTION ───────────────────────────────────────────────────────

def detect_currency(full_text):
    text_lower = full_text.lower()
    for symbol, code in CURRENCY_MAP.items():
        if symbol in text_lower or symbol in full_text:
            return code
    return 'EUR'

# ─── KEYWORD FUZZY MATCH ─────────────────────────────────────────────────────

def matches_keyword(line, keywords):
    line_lower = line.lower().strip()
    return any(kw in line_lower for kw in keywords)

def find_value_near_keyword(lines, keywords, offset=1):
    for i, line in enumerate(lines):
        if matches_keyword(line, keywords):
            # check same line first
            combined = line
            amount = extract_amount(combined)
            if amount:
                return amount, i
            # check next lines
            for j in range(1, offset + 2):
                if i + j < len(lines):
                    val = lines[i + j].strip()
                    amount = extract_amount(val)
                    if amount:
                        return amount, i + j
    return None, -1

# ─── TABLE DETECTION (pymupdf native) ────────────────────────────────────────

def extract_tables(doc):
    all_tables = []
    for page in doc:
        tabs = page.find_tables()
        for tab in tabs:
            df = tab.extract()
            if df and len(df) > 1:
                all_tables.append(df)
    return all_tables

def parse_line_items_from_tables(tables):
    items = []
    desc_keywords = ['description', 'service', 'item', 'subscription', 'leistung',
                     'bezeichnung', 'artikel', 'position', 'produit', 'désignation']
    amount_keywords = ['amount', 'price', 'total', 'betrag', 'preis', 'prix', 'montant', 'subtotal']

    for table in tables:
        if not table or len(table) < 2:
            continue
        headers = [str(h).lower().strip() if h else '' for h in table[0]]
        desc_col = next((i for i, h in enumerate(headers) if any(k in h for k in desc_keywords)), None)
        amount_col = next((i for i, h in enumerate(headers) if any(k in h for k in amount_keywords)), None)

        if desc_col is None:
            desc_col = 0
        if amount_col is None:
            amount_col = len(headers) - 1

        for row in table[1:]:
            if not row or all(not cell for cell in row):
                continue
            desc = str(row[desc_col]).strip() if row[desc_col] else None
            raw_amount = str(row[amount_col]).strip() if amount_col < len(row) and row[amount_col] else None

            # skip subtotal/total rows
            if desc and any(k in desc.lower() for k in ['total', 'subtotal', 'vat', 'mwst', 'tva', 'gesamt']):
                continue

            if desc and raw_amount:
                amount = extract_amount(raw_amount)
                # try quantity column
                qty = None
                qty_keywords = ['qty', 'quantity', 'menge', 'anzahl', 'quantité']
                qty_col = next((i for i, h in enumerate(headers) if any(k in h for k in qty_keywords)), None)
                if qty_col and qty_col < len(row) and row[qty_col]:
                    try:
                        qty = float(str(row[qty_col]).strip())
                    except:
                        qty = None

                if desc and len(desc) > 1:
                    items.append({
                        'name': desc,
                        'quantity': qty or 1,
                        'price': amount
                    })
    return items

# ─── POSITIONAL TEXT EXTRACTION ──────────────────────────────────────────────

def extract_blocks_by_position(doc):
    all_blocks = []
    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block.get("type") == 0:  # text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if text:
                            all_blocks.append({
                                "text": text,
                                "x": span["bbox"][0],
                                "y": span["bbox"][1],
                                "size": span.get("size", 0),
                                "bold": bool(span.get("flags", 0) & 2**4)
                            })
    return sorted(all_blocks, key=lambda b: (round(b["y"] / 10), b["x"]))

# ─── MAIN EXTRACTION ─────────────────────────────────────────────────────────

full_text = ""
for page in doc:
    full_text += page.get_text()

lines = [l.strip() for l in full_text.split("\n") if l.strip()]
blocks = extract_blocks_by_position(doc)
tables = extract_tables(doc)
currency = detect_currency(full_text)

# Invoice number
invoice_number = None
for i, line in enumerate(lines):
    if matches_keyword(line, INVOICE_NUMBER_KEYWORDS):
        # value on same line after keyword
        for kw in INVOICE_NUMBER_KEYWORDS:
            m = re.search(rf'{re.escape(kw)}[\s:#]*([A-Z0-9\-]+)', line, re.IGNORECASE)
            if m:
                invoice_number = m.group(1).strip()
                break
        # value on next line
        if not invoice_number and i + 1 < len(lines):
            candidate = lines[i + 1].strip()
            if re.match(r'^[A-Z0-9\-]{4,}$', candidate):
                invoice_number = candidate
        if invoice_number:
            break
# fallback: find standalone invoice-like number
if not invoice_number:
    for line in lines:
        m = re.search(r'\b([A-Z]{0,4}-?\d{6,})\b', line)
        if m:
            invoice_number = m.group(1)
            break

# Date
date = None
for i, line in enumerate(lines):
    if matches_keyword(line, DATE_KEYWORDS):
        search_lines = [line] + lines[i+1:i+3]
        for sl in search_lines:
            for pattern, fmt in DATE_PATTERNS:
                m = re.search(pattern, sl, re.IGNORECASE)
                if m:
                    date = normalize_date(m.group(1))
                    break
            if date:
                break
    if date:
        break
# fallback: find any date in document
if not date:
    for line in lines:
        for pattern, fmt in DATE_PATTERNS:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                date = normalize_date(m.group(1))
                break
        if date:
            break

# Total
total, _ = find_value_near_keyword(lines, TOTAL_KEYWORDS)
subtotal, _ = find_value_near_keyword(lines, SUBTOTAL_KEYWORDS)
vat, _ = find_value_near_keyword(lines, VAT_KEYWORDS)

# Vendor
vendor = None
bill_to_idx = next((i for i, l in enumerate(lines) if matches_keyword(l, BILL_TO_KEYWORDS)), None)
if bill_to_idx and bill_to_idx > 0:
    # vendor is the most prominent text before "bill to"
    for block in blocks:
        if block["bold"] and block["y"] < (blocks[bill_to_idx]["y"] if bill_to_idx < len(blocks) else 999):
            vendor = block["text"]
            break
    if not vendor:
        vendor = lines[0] if lines else None

# Client
client_name = None
client_email = None
client_company = None
client_address = None

if bill_to_idx is not None:
    client_block = lines[bill_to_idx+1:bill_to_idx+8]
    if client_block:
        client_name = client_block[0]
    if len(client_block) > 1:
        client_company = client_block[1]
    for line in client_block:
        if re.match(r'[^@\s]+@[^@\s]+\.[^@\s]+', line):
            client_email = line
        if re.search(r'\d{4,5}\s+\w+', line):
            client_address = line

# Line items from tables (preferred) or text fallback
services = parse_line_items_from_tables(tables)

# Text fallback if no table detected
if not services:
    for i, line in enumerate(lines):
        if matches_keyword(line, ['subtotal', 'total', 'gesamt', 'zwischensumme', 'montant']):
            continue
        amount = extract_amount(line)
        if amount and amount != total and amount != subtotal:
            desc = lines[i-1] if i > 0 else line
            if len(desc) > 2 and not extract_amount(desc):
                services.append({
                    'name': desc,
                    'quantity': 1,
                    'price': amount
                })

# Confidence score
score = 0
if invoice_number: score += 25
if date: score += 25
if total: score += 30
if services: score += 20
confidence = round(score / 100, 2)

result = {
    'invoiceNumber': invoice_number,
    'date': date,
    'currency': currency,
    'vendor': vendor,
    'client': {
        'name': client_name,
        'company': client_company,
        'email': client_email,
        'address': client_address
    },
    'services': services,
    'subtotal': subtotal,
    'vat': vat,
    'total': total,
    'confidence': confidence,
    'flags': {
        'needsReview': confidence < 0.7,
        'missingTotal': total is None,
        'missingDate': date is None,
        'noLineItems': len(services) == 0
    }
}

print(json.dumps(result, ensure_ascii=False))