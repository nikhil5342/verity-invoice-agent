"""
Verify the validation + decision logic WITHOUT calling Gemini.

Run:  python selftest.py
It feeds hand-written 'perfect extraction' dicts (as if the model read flawlessly)
so you can confirm the arithmetic and routing are right before wiring the model.
"""
from validate import load_context, run_checks
from decide import decide
import config

ctx = load_context(config.CONTEXT_DIR)
HIGH = {"vendor_name": 0.99, "invoice_amount": 0.99, "po_reference": 0.99}

# (extraction, expected_decision, expected_fraud)
CASES = [
    (dict(vendor_name="Acme Steel Co", invoice_amount=12000, po_reference="PO-1001",
          invoice_date="2026-05-02", bank_account_last4="4521",
          line_items=[dict(description="Steel beams", qty=100, unit_price=120, line_total=12000)],
          field_confidence=HIGH), "AUTO-CLEAR", "No"),

    (dict(vendor_name="BlueOcean Logistics", invoice_amount=9900, po_reference="PO-1002",
          invoice_date="2026-05-09", bank_account_last4="8830", line_items=[],
          field_confidence=HIGH), "FLAG", "No"),                      # PO amount mismatch

    (dict(vendor_name="Acme Steel Co", invoice_amount=13200, po_reference="PO-1001",
          invoice_date="2026-05-11", bank_account_last4="4521",
          line_items=[dict(description="Steel beams", qty=100, unit_price=120, line_total=12000)],
          field_confidence=HIGH), "FLAG", "No"),                      # total math error

    (dict(vendor_name="Pinnacle Consulting", invoice_amount=25000, po_reference="PO-1005",
          invoice_date="2026-05-12", bank_account_last4="0000", line_items=[],
          field_confidence=HIGH), "FLAG", "Yes"),                     # bank change -> fraud

    (dict(vendor_name="Acme Steel Corporation", invoice_amount=11500, po_reference="PO-1001",
          invoice_date="2026-05-14", bank_account_last4="7788", line_items=[],
          field_confidence=HIGH), "FLAG", "Yes"),                     # impersonation -> fraud

    (dict(vendor_name="Nimbus Software Ltd", invoice_amount=12800, po_reference="",
          invoice_date="2026-05-13", bank_account_last4="1209", line_items=[],
          field_confidence=HIGH), "FLAG", "Yes"),                     # anomaly + no PO

    (dict(vendor_name="QuickParts LLC", invoice_amount=5600, po_reference="",
          invoice_date="2026-05-18", bank_account_last4="5566", line_items=[],
          field_confidence=HIGH), "FLAG", "Yes"),                     # unknown vendor

    (dict(vendor_name="BlueOcean Logistics", invoice_amount=None, po_reference="PO-1002",
          invoice_date="2026-05-15", bank_account_last4="8830", line_items=[],
          field_confidence={"vendor_name": 0.9, "invoice_amount": 0.3, "po_reference": 0.4}),
     "ESCALATE", "No"),                                               # blurry -> escalate
]

passed = 0
for i, (ext, exp_dec, exp_fraud) in enumerate(CASES, 1):
    findings, _ = run_checks(ext, ctx)
    d = decide(ext, findings)
    ok = d.decision == exp_dec and d.fraud_flag == exp_fraud
    passed += ok
    print(f"[{'PASS' if ok else 'FAIL'}] case {i}: {d.decision}/{d.fraud_flag} "
          f"(expected {exp_dec}/{exp_fraud})")
    for r in d.reasons:
        print(f"        - {r}")

# Duplicate test: process a Crestline invoice, then an identical one.
hist = []
base = dict(vendor_name="Crestline Office Supplies", invoice_amount=1450,
            po_reference="PO-1004", invoice_date="2026-05-05",
            bank_account_last4="6677", line_items=[], field_confidence=HIGH)
from validate import _dup_key
run_checks(base, ctx, hist)
hist.append({"key": _dup_key(base), "month": base["invoice_date"][:7]})
dup = dict(base, invoice_date="2026-05-10")
d = decide(dup, run_checks(dup, ctx, hist)[0])
ok = d.decision == "FLAG" and d.fraud_flag == "Yes"
passed += ok
print(f"[{'PASS' if ok else 'FAIL'}] duplicate case: {d.decision}/{d.fraud_flag} (expected FLAG/Yes)")

print(f"\n{passed}/{len(CASES)+1} cases passed")
