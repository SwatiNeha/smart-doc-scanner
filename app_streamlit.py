import streamlit as st
import os
import requests
import pandas as pd
import io
import json
from typing import List

def _read_secret(key: str, default: str = "") -> str:
    # Try Streamlit secrets, else ENV, else default—without crashing if secrets.toml is missing
    try:
        # Only touch st.secrets if it exists
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)

API_BASE = _read_secret("API_BASE", "http://127.0.0.1:8001")
API_KEY  = _read_secret("API_KEY", "")

st.set_page_config(page_title="Smart Invoice Extractor", layout="wide")
st.title("Smart Invoice Extractor")

with st.sidebar:
    st.markdown("### Settings")
    api_base = st.text_input("API Base URL", API_BASE)
    api_key  = st.text_input("API Key (optional)", API_KEY, type="password")
    include_ocr = st.checkbox("Include OCR text in results", value=False)

st.write("Upload one or more receipt/invoice images (jpg, png, webp, tiff, bmp, pdf).")
files = st.file_uploader("Drag & drop or Browse", accept_multiple_files=True,
                         type=["png","jpg","jpeg","webp","tif","tiff","bmp","pdf"])

col1, col2 = st.columns([1,1])
with col1:
    run_single = st.button("Extract Single (first file)")
with col2:
    run_batch = st.button("Extract Batch")

def call_api_extract_single(api_base: str, key: str, f) -> dict:
    url = f"{api_base}/extract"
    headers = {"x-api-key": key} if key else {}
    files = {"file": (f.name, f.getvalue(), f.type or "application/octet-stream")}
    params = {"include_ocr_text": str(include_ocr).lower()}
    r = requests.post(url, headers=headers, files=files, params=params, timeout=90)
    r.raise_for_status()
    return r.json()

def call_api_extract_batch(api_base: str, key: str, fs: List) -> dict:
    url = f"{api_base}/extract-batch"
    headers = {"x-api-key": key} if key else {}
    mfiles = [("files", (f.name, f.getvalue(), f.type or "application/octet-stream")) for f in fs]
    params = {"include_ocr_text": str(include_ocr).lower()}
    r = requests.post(url, headers=headers, files=mfiles, params=params, timeout=300)
    r.raise_for_status()
    return r.json()

def results_to_dataframe(payload: dict) -> pd.DataFrame:
    rows = []
    for item in payload.get("results", []):
        if item.get("status") == "ok":
            row = {"filename": item["filename"], **item["fields"]}
            rows.append(row)
        else:
            rows.append({"filename": item.get("filename","?"), "error": item.get("error")})
    return pd.DataFrame(rows) if rows else pd.DataFrame()

if run_single:
    if not files:
        st.warning("Please upload at least one file.")
    else:
        with st.spinner("Processing single file..."):
            try:
                data = call_api_extract_single(api_base, api_key, files[0])
                st.subheader("Single Result")
                st.json(data)
            except Exception as e:
                st.error(f"Single extract failed: {e}")

if run_batch:
    if not files:
        st.warning("Please upload at least one file.")
    else:
        with st.spinner(f"Processing {len(files)} files..."):
            try:
                data = call_api_extract_batch(api_base, api_key, files)
                st.subheader("Summary")
                st.write(data.get("summary", {}))
                df = results_to_dataframe(data)
                if not df.empty:
                    st.subheader("Results")
                    st.dataframe(df, use_container_width=True)

                    # download CSV
                    csv = df.to_csv(index=False).encode("utf-8")
                    st.download_button("Download CSV", data=csv, file_name="extractions.csv", mime="text/csv")

                    # raw JSON download
                    raw = json.dumps(data, indent=2).encode("utf-8")
                    st.download_button("Download Raw JSON", data=raw, file_name="extractions.json", mime="application/json")
                else:
                    st.info("No rows to show (maybe all files errored?).")
            except Exception as e:
                st.error(f"Batch extract failed: {e}")
