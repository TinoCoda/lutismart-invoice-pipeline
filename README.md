# LütiSmart — Invoice Processing Pipeline

**Automated inbound invoice processing — from email attachment to structured data.**

When a supplier invoice arrives by email, this pipeline extracts the data, logs it in a relational Google Sheets structure, saves the original PDF to Google Drive, and sends a confirmation — all without touching it manually.

---

## 🎯 What it does

1. Gmail trigger fires when a new email with a PDF attachment arrives
2. n8n extracts the binary attachment and converts it to base64
3. A Python microservice uses pymupdf to extract structured data from the PDF
4. A JS node parses the extraction into a master record and line items
5. Google Sheets logs the invoice header (reference, vendor, total, date, status)
6. The invoice ID is read back to link line items as a foreign key
7. Each service/line item is logged in a separate detail sheet
8. Google Drive saves the original PDF
9. Gmail sends a confirmation with the extracted summary

---

## 🏗 Architecture

```
[Gmail Trigger]
(email with PDF attachment)
        ↓
[Extract from File Node]
(binary → base64)
        ↓
[HTTP Request]
→ python-runner/extractInvoice
(pymupdf → structured JSON)
        ↓
[JS Code Node — ParseJSON]
(master record + line items)
        ↓
[Google Sheets — Overview]       [Google Drive]
(log invoice header)             (save original PDF)
        ↓
[Google Sheets — Read]
(get last row ID)
        ↓
[JS Code Node — PrepareRows]
(map line items with foreign key)
        ↓
[Google Sheets — InvoiceDetails]
(log one row per line item)
        ↓
[Gmail]
(send confirmation email)
```

---

## 🛠 Stack

| Component | Technology |
|---|---|
| Automation | n8n (self-hosted) |
| PDF extraction | Python · pymupdf |
| Data storage | Google Sheets API (relational structure) |
| File storage | Google Drive API |
| Email | Gmail API · OAuth2 |
| Infrastructure | Docker · Nginx · Hetzner VPS · SSL |

---

## 📁 Repository contents

```
python/
  extractInvoice.py     # pymupdf extraction — basic regex parser
  extractInvoiceV2.py   # Advanced multilingual parser:
                        #   - Native table detection (pymupdf)
                        #   - Positional block analysis (x/y coordinates)
                        #   - Multilingual keywords (EN/DE/FR/ES)
                        #   - Date normalization to ISO 8601
                        #   - Currency detection
                        #   - Confidence scoring + review flags
```

The n8n workflow is not published — it is part of the LütiSmart production system.

---

## 🧠 PDF extraction approach

Two extraction strategies are included:

**V1 — Regex parser** (`extractInvoice.py`)
Works reliably on consistent invoice formats from known vendors. Fast and predictable.

**V2 — Multilingual positional parser** (`extractInvoiceV2.py`)
Handles unknown invoice formats across languages. Uses pymupdf's native table detection and block positioning to infer structure geometrically rather than by keyword matching. Returns a confidence score and flags invoices that need manual review.

For fully unknown vendor formats, the next step is LLM-based extraction via the Claude or OpenAI API.

---

## 📊 Data structure

**Overview sheet (master)**
| ID | Reference | Contact | Company | Email | Total | Date | Status |
|---|---|---|---|---|---|---|---|

**InvoiceDetails sheet (line items)**
| ID | Reference | Item | Count | Subtotal |
|---|---|---|---|---|

The ID column uses `=ROW()-1` — predictable, no UUID dependency, joinable across sheets.

---

## 🚀 Deployment

The full stack runs on a Hetzner VPS:
- n8n self-hosted via Docker Compose
- python-runner microservice (FastAPI + pymupdf) in a separate container
- Nginx reverse proxy with SSL (Let's Encrypt)

---

## 📬 Contact

[demo.lutismart.de](https://demo.lutismart.de) · info@lutismart.de