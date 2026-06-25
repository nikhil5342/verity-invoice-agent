# Verity — an AI employee for accounts payable

Verity reviews every invoice end-to-end — reads it, validates it against a vendor master and purchase orders, screens it for fraud — and routes **only the exceptions** to a human. It's a working prototype built to explore a specific thesis: in regulated finance, the bottleneck for autonomous AI isn't capability, it's **trust**. So the centerpiece isn't the model — it's calibrated escalation, deterministic validation, and a full audit trail.

> The accountant stops reviewing invoices and starts reviewing the agent's *exceptions*.

---

## Results at a glance

Evaluated on a labeled 50-invoice benchmark (35 clean, 15 problem), each label verified against the agent's own logic.

| Metric | Result | What it means |
|---|---|---|
| **Extraction accuracy** | **100%** | Read vendor and amount correctly on every invoice |
| **Fraud recall** | **100%** (7/7) | Caught every planted fraud |
| **Fraud precision** | **77.8%** (7/9) | 2 false alarms — both blurry scans (see finding below) |
| **Routing accuracy** | **94%** | Sent 47/50 invoices to the correct bucket |
| **Automation rate** | **72%** | Handled with zero human involvement |
| **Escaped-error rate** | **2.8%** (1/36) | Of auto-handled invoices, share that were wrong |

**The most valuable finding is an honest one.** Every invoice scored 100% self-reported confidence, so the `ESCALATE` path *never fired* — and all three errors were degraded scans the model read overconfidently instead of escalating. Capability is excellent; the real gap is **confidence calibration**. The evaluation set surfaced this before a customer ever could, which is exactly why it exists. The top roadmap item is an independent image-quality gate so low-quality scans escalate instead of getting a confident wrong answer.

---

## The core design decision

**The LLM reads. Deterministic code does the math.**

The model is used only for what it's uniquely good at — perception and language (reading fields off a messy invoice, writing a human-readable reason for a flag). Every calculation and rule is plain Python: vendor and PO matching, line/total footing, bank-detail checks, anomaly thresholds, and duplicate detection. That keeps every decision **exact, repeatable, and auditable** — the difference between a demo and something a finance team could actually deploy.

Three decisions, never blurred:

| Decision | Meaning | Action |
|---|---|---|
| `AUTO-CLEAR` | Confident the invoice is good | No human needed |
| `FLAG` | Confident it found a problem | Human reviews, with evidence |
| `ESCALATE` | Not confident it *read* it correctly | Human verifies |

`FLAG` ("I found a problem") and `ESCALATE` ("I'm not sure I read it") are different signals with different human actions — and they're kept strictly separate. Every extraction and decision is written to an append-only audit log, so nothing happens off the record.

---

## How it works

```
Invoice ──> Extract ──────> Validate ─────────> Decide ──────> AUTO-CLEAR / FLAG / ESCALATE
            (Gemini reads    (Python checks      (confidence              │
             fields +         vs vendor master    + findings)             ▼
             confidence)      & purchase orders)                   Audit log + human gate
```

Five layers, each with a clear job:

- **Model** — a vision LLM (Gemini 3.1 Flash-Lite) extracts structured fields with per-field confidence
- **Context** — the customer's vendor master and purchase orders, the source of truth (direct lookups, not RAG — the data is small and structured)
- **Orchestration** — deterministic checks run the matching, math, anomaly, and duplicate logic
- **Governance** — confidence + findings map to a decision; everything is logged
- **Human** — reviews exceptions and gates payment; autonomy widens as the audit trail proves the agent right

---

## What it catches

Fraud: bank-account changes, vendor impersonation (look-alike names), phantom vendors, duplicate invoices (keyed on vendor + PO + amount against history, with a recurring-PO exception), and amount anomalies vs. a vendor's history. Errors: overbilling vs. PO, quantity over PO, totals that don't foot, inflated tax, and invalid PO references. Each flag carries its evidence — e.g. *"bank account ...0000 differs from the vendor master (...9012)."*

---

## Tech stack

Python · Google Gemini (`google-genai` SDK) · Pydantic (structured-output validation) · Streamlit (review UI) · append-only JSONL audit log · CSV-based context store.

---

## Project structure

```
verity/
├── app.py              # Streamlit UI — upload an invoice, see the decision + evidence
├── extract.py          # Gemini vision extraction (read-only, reports confidence)
├── validate.py         # Deterministic checks: vendor/PO match, math, bank, anomaly, duplicate
├── decide.py           # Confidence + findings -> AUTO-CLEAR / FLAG / ESCALATE
├── audit.py            # Append-only audit log
├── run_eval.py         # Batch-score a folder of invoices
├── rebuild_results.py  # Recover results from the audit log without re-running the model
├── selftest.py         # Sanity checks for the decision logic
├── config.py           # Reads settings from environment (no secrets in code)
├── context/
│   ├── vendors.csv     # Vendor master (source of truth)
│   └── pos.csv         # Purchase orders
└── invoices/           # Synthetic test invoices
```

---

## Getting started

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Add your config.** Create a `.env` file (this is git-ignored — never commit it):
```
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.1-flash-lite
```
Get a free key from [Google AI Studio](https://aistudio.google.com/). See `.env.example` for the expected variables.

**3. Run the review UI**
```bash
streamlit run app.py
```
Upload an invoice and watch Verity extract, validate, and decide — with the evidence behind every call.

**4. Run the batch evaluation**
```bash
python run_eval.py
```
Scores every invoice in `invoices/` and writes `eval_results.csv`. Compare against the answer key to reproduce the metrics above.

---

## Evaluation framework

The eval is organized around three questions an AI PM has to answer:

1. **Did it perceive correctly?** — extraction accuracy
2. **Did it decide correctly?** — routing accuracy, fraud precision and recall
3. **Can you trust what it owns?** — automation rate and, most importantly, **escaped-error rate** (of the invoices auto-handled with no human, how often it was wrong)

A high automation rate only counts if the auto-handled bucket is near-perfect — otherwise you've just moved errors somewhere nobody is looking. That's why escaped-error rate, not raw automation, is the metric that matters.

---

## Roadmap

- **Confidence calibration** — an independent image-quality / OCR-confidence signal so degraded scans escalate instead of being guessed (the #1 fix)
- **3-way matching** — add goods-receipt matching for full invoice ↔ PO ↔ receipt verification
- **More workflows** — extend the same engine to PO matching, expense reconciliation, and month-end close
- **Learning loop** — feed every human approve/reject decision back into the eval set
- **Integrations** — pull invoices from email; post results to the ERP

---

## A note on the data

All invoices, vendors, and purchase orders in this repo are **synthetic**, generated specifically to stress-test the agent across clean cases, fraud scenarios, and degraded scans. No real financial data is used.

---

*Built as a hands-on exploration of AI product management — the architecture, the evaluation discipline, and the judgment calls behind shipping an autonomous agent into a domain where getting it wrong isn't an option.*
