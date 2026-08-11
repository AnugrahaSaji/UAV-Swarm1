#!/usr/bin/env python3
"""Extract text from all reference PDFs for validation."""
import os, sys, json

REFDIR = r"c:\Users\burak\ptojects\secure-tunnel\paper\references"

try:
    import pdfplumber
    USE = "pdfplumber"
except ImportError:
    from pdfminer.high_level import extract_text
    USE = "pdfminer"

results = {}
for fname in sorted(os.listdir(REFDIR)):
    if not fname.endswith(".pdf") or not fname[0].isdigit():
        continue
    fpath = os.path.join(REFDIR, fname)
    try:
        if USE == "pdfplumber":
            with pdfplumber.open(fpath) as pdf:
                pages = []
                for i, page in enumerate(pdf.pages):
                    if i >= 5:  # First 5 pages enough for validation
                        break
                    text = page.extract_text() or ""
                    pages.append(text)
                full = "\n---PAGE---\n".join(pages)
        else:
            full = extract_text(fpath, maxpages=5)
        
        results[fname] = full[:6000]  # Cap at 6000 chars per doc
        print(f"OK  {fname}: {len(full)} chars extracted")
    except Exception as e:
        print(f"ERR {fname}: {e}")
        results[fname] = f"EXTRACTION ERROR: {e}"

# Save extracted text
outpath = os.path.join(REFDIR, "_extracted_text.json")
with open(outpath, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\nSaved {len(results)} extractions to {outpath}")
