import streamlit as st
import pytesseract
from PIL import Image
import openai
import re
import json
import numpy as np
import cv2
import os

# --- GROQ LLM CONFIGURATION ---

openai.api_base = "https://api.groq.com/openai/v1"
openai.api_key = os.getenv("GROQ_API_KEY")  # set in Streamlit Cloud secrets
llm_model = "llama3-8b-8192"  # or "mixtral-8x7b-32768"

Path to tesseract executable (adjust if needed)
#pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

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

st.title("📄 Smart Invoice Extractor (LLM Powered)")

uploaded_file = st.file_uploader("Upload an invoice image (.jpg, .png)", type=['jpg', 'jpeg', 'png'])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption='Uploaded Invoice', use_column_width=True)

    # --- Robust OCR Preprocessing Step ---
    with st.spinner("Extracting text with OCR (preprocessing image)..."):
        # Convert PIL Image to OpenCV format (numpy array)
        img_array = np.array(image.convert("RGB"))
        img_cv = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        # Grayscale
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        # Resize (scaling up for better OCR if image is small)
        scale_factor = 2
        gray = cv2.resize(gray, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_LINEAR)
        # Binarize (Otsu's threshold)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        
        # Optional: show preprocessed image for debugging
        st.image(thresh, caption="Preprocessed (Thresholded) for OCR", use_column_width=True, channels="GRAY")
        
        # Run OCR on processed image
        pil_img = Image.fromarray(thresh)
        custom_config = r'--oem 3 --psm 6'
        ocr_text = pytesseract.image_to_string(pil_img, lang="eng", config=custom_config)

    st.subheader("🔍 OCR Text")
    st.code(ocr_text, language="text")

    # --- LLM Extraction ---
    with st.spinner("Extracting invoice fields using LLM..."):
        prompt = prompt_template.format(invoice_text=ocr_text)
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
            content = response["choices"][0]["message"]["content"]
        except Exception as e:
            st.error(f"LLM extraction failed: {e}")
            content = ""

        # --- Robust JSON extraction ---
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
            st.warning("Could not parse LLM output as JSON. Showing raw response:")
            st.code(content)
        else:
            st.subheader("📋 Extracted Invoice Fields")
            st.json(data)
