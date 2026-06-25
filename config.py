"""Central config. Everything tunable lives here so you change it in one place."""
import os
from dotenv import load_dotenv

load_dotenv()  # reads the .env file next to this script

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# NOTE: model IDs change often. Confirm the current Gemini model string at
# https://ai.google.dev/gemini-api/docs/models  (e.g. a Pro tier for accuracy,
# a Flash tier for speed/cost). Override via .env without touching code.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# The DIAL from your eval doc: raise it -> escalate more (safer, less automation);
# lower it -> automate more (but more escaped errors). Tune it with your eval set.
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.85"))

BASE = os.path.dirname(os.path.abspath(__file__))
CONTEXT_DIR = os.path.join(BASE, "context")
INVOICE_DIR = os.path.join(BASE, "invoices")
AUDIT_LOG = os.path.join(BASE, "audit_log.jsonl")
