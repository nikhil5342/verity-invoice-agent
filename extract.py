import time, random

RETRYABLE = {429, 500, 503, 504}

def _status(err):
    for a in ("code", "status_code"):
        v = getattr(err, a, None)
        if isinstance(v, int):
            return v
    return getattr(getattr(err, "response", None), "status_code", None)


"""
MODEL + CONTEXT: read the invoice with Gemini.

The model's ONLY job is to read what is printed and report its confidence.
It does NOT validate, correct math, or guess - that is the deterministic layer's job.
"""
import json
import mimetypes
from typing import Optional, List
from pydantic import BaseModel, ValidationError
import fitz  # PyMuPDF
from google import genai
from google.genai import types
import config

PROMPT = """You are an invoice data extractor. Read the attached invoice image and return ONLY valid JSON (no prose, no markdown) matching this schema:

{
  "vendor_name": string,
  "invoice_amount": number,            // the final total
  "line_items": [{"description": string, "qty": number, "unit_price": number, "line_total": number}],
  "invoice_date": "YYYY-MM-DD",
  "po_reference": string or null,      // null if none printed
  "bank_account_last4": string or null,
  "field_confidence": {                // 0.0-1.0: how sure you are you READ each field correctly
    "vendor_name": number,
    "invoice_amount": number,
    "po_reference": number
  }
}

Rules:
- Report values AS PRINTED. Do NOT correct math, do NOT validate, do NOT guess.
- If a field is illegible or absent, set it to null and its confidence below 0.5.
- Do not infer a PO number that is not visibly printed."""


# --- structured-output validation (a guardrail: reject malformed model output) ---
class _Conf(BaseModel):
    vendor_name: float = 0.0
    invoice_amount: float = 0.0
    po_reference: float = 0.0

class _Line(BaseModel):
    description: str = ""
    qty: float = 0
    unit_price: float = 0
    line_total: float = 0

class Extraction(BaseModel):
    vendor_name: Optional[str] = None
    invoice_amount: Optional[float] = None
    line_items: List[_Line] = []
    invoice_date: Optional[str] = None
    po_reference: Optional[str] = None
    bank_account_last4: Optional[str] = None
    field_confidence: _Conf = _Conf()


def file_to_image(path):
    """Return (image_bytes, mime_type). Renders the first PDF page to PNG."""
    if path.lower().endswith(".pdf"):
        doc = fitz.open(path)
        pix = doc[0].get_pixmap(dpi=200)
        return pix.tobytes("png"), "image/png"
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        return f.read(), mime


def _strip_fences(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip()


def extract_invoice(path):
    """Read an invoice file and return a validated dict."""
    img, mime = file_to_image(path)
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    resp = None
    delay = 1.0
    for attempt in range(6):
        try:
            resp = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=[types.Part.from_bytes(data=img, mime_type=mime), PROMPT],
                config=types.GenerateContentConfig(temperature=0, response_mime_type="application/json"),
            )
            break
        except Exception as e:
            if _status(e) in RETRYABLE and attempt < 5:
                wait = min(delay * (2 ** attempt), 30) + random.uniform(0, 0.5)
                print(f"  transient {_status(e)}; retrying in {wait:.1f}s")
                time.sleep(wait)
            else:
                raise
    raw = _strip_fences(resp.text)
    try:
        data = json.loads(raw)
        return Extraction(**data).model_dump()
    except (json.JSONDecodeError, ValidationError) as e:
        # Guardrail: malformed output is a failure to catch, not to ignore.
        raise ValueError(f"Model returned output we could not parse: {e}\n---\n{raw}")
