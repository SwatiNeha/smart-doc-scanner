import os
import csv
import json

import openai

# --- OLLAMA LOCAL LLM CONFIGURATION ---
openai.api_base = "http://localhost:11434/v1"    # Ollama's default API endpoint
openai.api_key = "ollama"                        # Dummy, Ollama ignores but openai library needs it
llm_model = "gemma3:latest"                             # Change to the model you are running (e.g. "gemma:2b")

# --- PROJECT PATHS ---
samples_folder = "samples"                       # Folder with your .txt OCR outputs
output_path = "llm_invoice_fields.csv"

# --- PROMPT TEMPLATE ---
prompt_template = """
You are an invoice data extraction agent.
Given the following raw OCR text from an invoice, extract these fields:
- invoice_number
- invoice_date
- due_date
- subtotal
- tax_rate
- tax_amount
- total
- balance_due
- cash
- change
- gst_id

If any field is missing, use "NOT FOUND".
Output ONLY a valid JSON object with these keys.

Invoice Text:
------
{invoice_text}
------
"""

# --- CSV OUTPUT HEADERS ---
fieldnames = [
    "filename", "invoice_number", "invoice_date", "due_date", "subtotal",
    "tax_rate", "tax_amount", "total", "balance_due", "cash", "change", "gst_id"
]
rows = []

# --- MAIN BATCH PROCESSING LOOP ---
for filename in os.listdir(samples_folder):
    if filename.endswith(".txt"):
        with open(os.path.join(samples_folder, filename), "r", encoding="utf-8") as f:
            invoice_text = f.read()

        prompt = prompt_template.format(invoice_text=invoice_text)

        print(f"Processing: {filename} using Ollama local LLM...")

        try:
            response = openai.ChatCompletion.create(
                model=llm_model,
                messages=[
                    {"role": "system", "content": "You are a helpful invoice extraction assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=512,
            )
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            continue

        import re

        content = response["choices"][0]["message"]["content"]

        # --- Robust JSON extraction function ---
        def extract_first_json(text):
            json_blocks = re.findall(r"```(?:json)?\s*([\s\S]+?)\s*```", text, flags=re.IGNORECASE)
            for jb in json_blocks:
                try:
                    return json.loads(jb)
                except Exception:
                    continue
            brace_blocks = re.findall(r"(\{[\s\S]+?\})", text)
            for bb in brace_blocks:
                try:
                    return json.loads(bb)
                except Exception:
                    continue
            return None

        data = extract_first_json(content)
        if not data or not isinstance(data, dict):
            print(f"Warning: Could not parse JSON for {filename}. LLM output was:\n{content}\n")
            data = {k: "NOT FOUND" for k in fieldnames[1:]}

        # --- Build Output Row ---
        row = {"filename": filename.replace('.txt', '.jpg')}
        for fn in fieldnames[1:]:
            row[fn] = data.get(fn, "NOT FOUND")
        rows.append(row)

# --- Save All Results to CSV ---
with open(output_path, "w", newline='', encoding="utf-8") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print("Ollama LLM extraction complete! Results in:", output_path)
