import os
import re
import csv

samples_folder = "samples"

# Patterns for each field
patterns = {
    "invoice_number": [
        r"Invoice\s*No\.?\s*[:\-]*\s*-?\s*([A-Za-z0-9\-]+)",
        r"INVOICE\s*#\s*\[([A-Za-z0-9\-]+)\]",
        r"INVOICE\s*#\s*([A-Za-z0-9\-]+)",
        r"INVOICE\s*NO\.?\s*[:\-]*\s*([A-Za-z0-9\-]+)",
        r"Invoice\s+([A-Za-z0-9\-]+)",
        r"Receipt\s*#\s*([A-Za-z0-9\-]+)",
        r"Receipt#([A-Za-z0-9\-]+)",
        r"TAX\s*INVOICE\s*NO\.?\s*[:\-]*\s*([A-Za-z0-9\-]+)",
        r"INVA[_\s\-:]*([A-Za-z0-9\-]+)",
    ],
    "invoice_date": [
        r"INVOICE\s*DATE[:\s\-]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
        r"Issue\s*date[:\s\-]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
        r"Date\s*[:\-]*\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
    ],
    "due_date": [
        r"Due\s*date[:\s\-]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
        r"DUE\s*DATE[:\s\-]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})",
    ],
    "subtotal": [
        r"Subtotal[\s:\$]*([0-9,]+\.[0-9]{2})",
        r"Sub\s*Total[\s:\$]*([0-9,]+\.[0-9]{2})",
    ],
    "tax_rate": [
        r"(?:Tax\s*Rate|Sales\s*Tax|GST|@)[^\d]*([0-9]{1,2}(?:\.[0-9]+)?%)",
        r"([0-9]{1,2}(?:\.[0-9]+)?%)\s*(?:GST|Tax)?",
    ],
    "tax_amount": [
        r"(?:Total\s*GST(?:\s*\(RM\))?|GST\s*RM|GST\s*Amount|GST)[\s:\(]*([0-9,]+\.[0-9]{2})",
        r"(?:Tax\s*|GST\s*Summary|Tax\s*\(RM\)|Tax)[\s:\-]?\s*([0-9,]+\.[0-9]{2})",
    ],
    "total": [
        r"TOTAL\s*(?:\(AUD\))?[\s:\$]*([0-9,]+\.[0-9]{2})",
        r"Total\s*Amount\s*Payable[\s:\$]*([0-9,]+\.[0-9]{2})",
        r"Total\s*incl\.? GST[\s:\$]*([0-9,]+\.[0-9]{2})",
        r"Total\s*\(RM\)[\s:\$]*([0-9,]+\.[0-9]{2})",
    ],
    "balance_due": [
        r"Balance\s*Due[\s:\$]*([0-9,]+\.[0-9]{2})",
        r"Amount\s*Due[\s:\$]*([0-9,]+\.[0-9]{2})",
    ],
    "cash": [
        r"Cash\s*[:\-]*([0-9,]+\.[0-9]{2})"
    ],
    "change": [
        r"Change(?:\s*Due)?\s*[:\-]*([0-9,]+\.[0-9]{2})"
    ],
    "gst_id": [
        r"(?:GST\s*(?:ID|Reg)\s*No\.?\s*[:\-]?\s*)([A-Za-z0-9\-]+)",
        r"QST\s*ID\s*[:\-]*\s*([A-Za-z0-9\-]+)"
    ]
}

def extract_field(text, pattern_list, field_name=None):
    """Tries all patterns in order; returns first match or 'NOT FOUND'."""
    for pattern in pattern_list:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            # Basic junk filter for invoice_number (tweak as needed)
            if field_name == "invoice_number" and value.upper() in {"MFY", "TAX", "CASH"}:
                continue
            return value
    return "NOT FOUND"

# Output
csv_path = os.path.join(samples_folder, "extracted_invoice_fields.csv")
fieldnames = ["filename"] + list(patterns.keys())
rows = []

for filename in os.listdir(samples_folder):
    if filename.lower().endswith('.txt'):
        file_path = os.path.join(samples_folder, filename)
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        row = {"filename": filename.replace('.txt', '.jpg')}
        for field, plist in patterns.items():
            row[field] = extract_field(text, plist, field)
        rows.append(row)

with open(csv_path, "w", newline='', encoding="utf-8") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print("Batch extraction complete! Check extracted_invoice_fields.csv")
