# Verity — AI Invoice Processing Agent

An "AI employee" for accounts payable. It reviews every invoice end-to-end — reads it,
validates it against the source of truth, screens for fraud — and routes only the
exceptions to a human. Built around one principle:

> **The model reads. Deterministic code does the math and the rules.**

## Architecture (the five layers)

| File | Layer | Does |
|------|-------|------|
| `extract.py` | Model + Context | Gemini reads the invoice → structured JSON + per-field confidence |
| `context/` | Context | Vendor master + purchase orders (the source of truth) |
| `validate.py` | Orchestration | Deterministic checks: vendor, PO match, math, bank, anomaly, duplicate |
| `decide.py` | Governance | Confidence + findings → AUTO-CLEAR / FLAG / ESCALATE |
| `audit.py` | Governance | Append-only log of every step |
| `run_eval.py` | Governance | Runs all 20 invoices → results for your scoring sheet |
| `app.py` | Human Layer | Review UI; human gates the payment |

**Two reasons an invoice reaches a human, kept separate:** `FLAG` = "I read it and found
a problem." `ESCALATE` = "I'm not confident I read it correctly." The
`CONFIDENCE_THRESHOLD` in `.env` is the dial between automation and safety.

## Setup

1. **Install Python 3.11+** and create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **Get a Gemini API key** from Google AI Studio: https://aistudio.google.com/apikey
3. **Create your `.env`** from the template and paste your key:
   ```bash
   cp .env.example .env
   ```
   Confirm the current model id at https://ai.google.dev/gemini-api/docs/models
   (a Pro tier is more accurate; a Flash tier is cheaper/faster).

## Run it

- **Verify the logic first (no API key needed):**
  ```bash
  python selftest.py
  ```
  All 9 cases should pass — this proves the validation/decision core before you spend a token.

- **Add invoice files** to `invoices/`, named by ID: `INV-001.pdf`, `INV-002.png`, …

- **Launch the review app:**
  ```bash
  streamlit run app.py
  ```

- **Run the full eval** (writes `eval_results.csv` for your scoring sheet):
  ```bash
  python run_eval.py
  ```

## How to work in Cursor

1. **Open the folder:** Cursor → File → Open Folder → select `verity/`. The whole repo
   is now in context.
2. **Understand before changing:** open any file, select code, press **Cmd/Ctrl+L** to
   open chat, and ask "explain what this function does." Great way to learn the codebase.
3. **Make changes by asking, then REVIEW the diff:** press **Cmd/Ctrl+K** in a file (or use
   chat) and describe the change, e.g. *"add a check in validate.py that flags invoices
   dated in the future."* Cursor proposes a diff — read it, then Accept or Reject. Never
   accept code you don't understand; ask it to explain first.
4. **Run things in Cursor's terminal:** Terminal → New Terminal, then run the commands
   above. Keep the agent in **review-driven** mode so you approve each step — the same
   "human stays in the loop" principle this product is built on.
5. **Good first asks for Cursor:**
   - "Walk me through `run_eval.py` line by line."
   - "The model sometimes returns the amount as a string — make `extract.py` more robust."
   - "Add a 'future-dated invoice' check and a self-test case for it."

## What's deliberately simple (and what you'd add for production)

- Context is small structured CSVs, so we use plain lookups — **no vector RAG needed.**
  Knowing when *not* to reach for RAG is a real product judgment.
- First PDF page only; multi-page invoices would loop pages.
- Duplicate history lives in memory per run; production would persist it.
