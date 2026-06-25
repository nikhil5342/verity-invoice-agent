"""
Run the agent over every invoice in invoices/ and write results to eval_results.csv,
in the column order your scoring sheet expects. Paste those columns into the yellow
cells of 03_Invoice_Eval_Set.xlsx.

Usage:  python run_eval.py
Invoice files should be named by their ID, e.g. INV-001.pdf, INV-002.png ...
"""
import csv
import glob
import os
from extract import extract_invoice
from validate import load_context, run_checks, _dup_key
from decide import decide
import audit
import config
import time

ctx = load_context(config.CONTEXT_DIR)


def main():
    files = sorted(
        f for f in glob.glob(os.path.join(config.INVOICE_DIR, "*"))
        if f.lower().endswith((".pdf", ".png", ".jpg", ".jpeg"))
    )
    if not files:
        print(f"No invoice files in {config.INVOICE_DIR}. Add INV-001.pdf, etc.")
        return

    history = []
    rows = []
    for path in files:
        inv_id = os.path.splitext(os.path.basename(path))[0]
        try:
            ext = extract_invoice(path)
        except Exception as e:
            print(f"[{inv_id}] extraction error: {e}")
            continue
        audit.log(inv_id, "extract", ext)
        findings, checks = run_checks(ext, ctx, history)
        audit.log(inv_id, "validate", checks)
        d = decide(ext, findings)
        audit.log(inv_id, "decide", d.__dict__)
        history.append({"key": _dup_key(ext), "month": (ext.get("invoice_date") or "")[:7]})

        rows.append({
            "Invoice ID": inv_id,
            "Agent Vendor": ext.get("vendor_name"),
            "Agent Amt": ext.get("invoice_amount"),
            "Agent Decision": d.decision,
            "Agent Fraud": d.fraud_flag,
            "Agent Conf %": int(d.confidence * 100),
            "Reasons": " | ".join(d.reasons),
        })
        print(f"[{inv_id}] {d.decision} / fraud={d.fraud_flag} / conf={d.confidence}")
        time.sleep(5)

    out = os.path.join(config.BASE, "eval_results.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {out} - paste into the scoring sheet's yellow columns.")


if __name__ == "__main__":
    main()
