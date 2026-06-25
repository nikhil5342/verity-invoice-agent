"""
Rebuild eval_results.csv from audit_log.jsonl WITHOUT re-running the agent.

Use this when run_eval.py processed every invoice (so the audit log is complete)
but writing the CSV failed. No model calls are made - this only reads the log,
so it uses zero API quota and is instant.

Usage:  python rebuild_results.py
"""
import json, csv, os
import config

# 1. Read every line of the append-only audit log.
records = []
with open(config.AUDIT_LOG, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # skip any half-written line

# 2. Keep the LATEST extract + decide per invoice.
#    The log is append-only, so a later line is the more recent run.
latest = {}
for rec in records:
    iid = rec.get("invoice_id"); stage = rec.get("stage")
    if stage in ("extract", "decide"):
        latest.setdefault(iid, {})[stage] = rec.get("payload", {})

# 3. Rebuild the rows (same columns run_eval.py would have written).
rows = []
for iid in sorted(latest):
    dec = latest[iid].get("decide")
    if not dec:
        continue  # invoice errored before a decision was logged
    ext = latest[iid].get("extract", {}) or {}
    conf = dec.get("confidence", 0)
    rows.append({
        "Invoice ID": iid,
        "Agent Vendor": ext.get("vendor_name"),
        "Agent Amt": ext.get("invoice_amount"),
        "Agent Decision": dec.get("decision"),
        "Agent Fraud": dec.get("fraud_flag"),
        "Agent Conf %": int(round(conf * 100)) if isinstance(conf, (int, float)) else conf,
        "Reasons": " | ".join(dec.get("reasons", []) or []),
    })

if not rows:
    print("No decisions found in the audit log. Did run_eval.py actually run?")
    raise SystemExit

# 4. Write the CSV. If it's locked (open in Excel), fall back to a new name.
out = os.path.join(config.BASE, "eval_results.csv")
try:
    fh = open(out, "w", newline="", encoding="utf-8")
except PermissionError:
    out = os.path.join(config.BASE, "eval_results_recovered.csv")
    fh = open(out, "w", newline="", encoding="utf-8")
with fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

# 5. Also print to the terminal, so you can copy/paste even if the file won't open.
print(f"Rebuilt {len(rows)} rows -> {out}\n")
print("Invoice\tDecision\tFraud\tConf%")
for r in rows:
    print(f"{r['Invoice ID']}\t{r['Agent Decision']}\t{r['Agent Fraud']}\t{r['Agent Conf %']}")
