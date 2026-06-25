"""
ORCHESTRATION + CONTEXT (deterministic).

This is the trust core. The LLM only READS the invoice; every check here is plain
Python so it is exact, repeatable, and auditable. None of these functions call a model.

Each check returns Finding objects. A Finding with failed=True means a human should
look. fraud=True means it looks like deception (not just an error).
"""
import csv
import difflib
from dataclasses import dataclass
from typing import Optional

MONEY_TOL = 0.5  # dollars; absorbs rounding noise


@dataclass
class Finding:
    check: str
    failed: bool
    fraud: bool
    reason: str


def money_equal(a, b, tol=MONEY_TOL):
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def load_context(context_dir):
    """Read the source-of-truth CSVs into memory."""
    with open(f"{context_dir}/vendors.csv") as f:
        vendors = list(csv.DictReader(f))
    for v in vendors:
        v["hist_avg"] = float(v["hist_avg"])
    with open(f"{context_dir}/pos.csv") as f:
        pos = list(csv.DictReader(f))
    for p in pos:
        p["auth_qty"] = float(p["auth_qty"])
        p["po_amount"] = float(p["po_amount"])
        p["recurring"] = p["recurring"].strip().lower() == "yes"
    return {"vendors": vendors, "pos": pos}


def resolve_vendor(extraction, vendors):
    """Return (finding_or_None, matched_vendor_or_None).

    Exact match -> no problem. Close-but-not-exact -> impersonation (fraud).
    No close match -> unknown vendor (fraud).
    """
    name = (extraction.get("vendor_name") or "").strip()
    if not name:
        return Finding("vendor_missing", True, False, "No vendor name could be read"), None

    norm = name.lower()
    for v in vendors:
        if v["vendor_name"].lower() == norm:
            return None, v  # known vendor, all good

    best, best_ratio = None, 0.0
    for v in vendors:
        r = difflib.SequenceMatcher(None, norm, v["vendor_name"].lower()).ratio()
        if r > best_ratio:
            best, best_ratio = v, r

    if best_ratio >= 0.70:
        return Finding(
            "vendor_impersonation", True, True,
            f"Vendor '{name}' closely resembles approved vendor "
            f"'{best['vendor_name']}' but is not an exact match - possible impersonation",
        ), best
    return Finding(
        "unknown_vendor", True, True,
        f"Vendor '{name}' is not in the approved vendor master - unverified payee",
    ), None


def check_po(extraction, pos):
    out = []
    ref = (extraction.get("po_reference") or "").strip()
    amt = extraction.get("invoice_amount")
    if not ref:
        out.append(Finding("po_missing", True, False,
                           "No PO reference printed - nothing to match against"))
        return out
    match = next((p for p in pos if p["po_number"].lower() == ref.lower()), None)
    if not match:
        out.append(Finding("po_not_found", True, False,
                           f"PO {ref} is not in the open purchase orders"))
        return out
    if amt is not None and not money_equal(amt, match["po_amount"]):
        out.append(Finding("po_amount_mismatch", True, False,
                           f"Invoice ${amt:,.0f} does not match PO {ref} "
                           f"(${match['po_amount']:,.0f})"))
    # light quantity check when single-line
    items = extraction.get("line_items") or []
    if items and not match["recurring"]:
        total_qty = sum((it.get("qty") or 0) for it in items)
        if total_qty and total_qty != match["auth_qty"]:
            out.append(Finding("po_qty_mismatch", True, False,
                               f"Invoice quantity {total_qty:g} exceeds PO authorized "
                               f"quantity {match['auth_qty']:g}"))
    return out


def check_math(extraction):
    out = []
    items = extraction.get("line_items") or []
    amt = extraction.get("invoice_amount")
    if not items:
        return out
    line_sum = 0.0
    for it in items:
        q = it.get("qty") or 0
        u = it.get("unit_price") or 0
        lt = it.get("line_total") or 0
        if not money_equal(q * u, lt):
            out.append(Finding("line_math", True, False,
                               f"Line '{it.get('description','?')}': {q:g} x ${u:,.0f} "
                               f"= ${q*u:,.0f}, but the line total reads ${lt:,.0f}"))
        line_sum += lt
    if amt is not None and not money_equal(line_sum, amt):
        out.append(Finding("total_math", True, False,
                           f"Line items sum to ${line_sum:,.0f}, but the invoice "
                           f"total reads ${amt:,.0f}"))
    return out


def check_bank(extraction, vendor):
    inv_bank = (extraction.get("bank_account_last4") or "").strip()
    master = (vendor.get("bank_last4") or "").strip()
    if inv_bank and master and inv_bank != master:
        return [Finding("bank_mismatch", True, True,
                        f"Bank account ...{inv_bank} differs from the vendor master "
                        f"(...{master}) - classic invoice-fraud signal")]
    return []


def check_anomaly(extraction, vendor):
    amt = extraction.get("invoice_amount")
    avg = vendor.get("hist_avg")
    if amt and avg and amt > 3 * avg:
        return [Finding("amount_anomaly", True, True,
                        f"Amount ${amt:,.0f} is {amt/avg:.1f}x this vendor's historical "
                        f"average (${avg:,.0f})")]
    return []


def _dup_key(extraction):
    return (
        (extraction.get("vendor_name") or "").strip().lower(),
        (extraction.get("po_reference") or "").strip().lower(),
        round(float(extraction.get("invoice_amount") or -1), 2),
    )


def check_duplicate(extraction, ctx, history):
    """history is a list of {'key':..., 'month':'YYYY-MM'} for already-seen invoices.

    A duplicate is an invoice identical to a prior one. Exception: a RECURRING PO
    (e.g. monthly cleaning) legitimately produces one invoice per period, so an
    identical amount in a *different month* is not a duplicate.
    """
    ref = (extraction.get("po_reference") or "").strip().lower()
    po = next((p for p in ctx["pos"] if p["po_number"].lower() == ref), None)
    recurring = bool(po and po["recurring"])
    month = (extraction.get("invoice_date") or "")[:7]
    key = _dup_key(extraction)
    for h in history:
        if h["key"] == key:
            if recurring and month and h["month"] and month != h["month"]:
                continue  # legit different-period invoice on a recurring PO
            return [Finding("duplicate", True, True,
                            "Identical to a previously processed invoice (same vendor, "
                            "PO, and amount) - duplicate-payment risk")]
    return []


    return []


CHECK_LABELS = {
    "vendor_name": "Vendor Name Check",
    "po_reference": "PO Reference Check",
    "po_amount": "PO Amount Check",
    "po_qty": "PO Quantity Check",
    "line_math": "Line Item Math Check",
    "total_math": "Invoice Total Math Check",
    "bank_account": "Bank Account Check",
    "amount_anomaly": "Amount Anomaly Check",
    "duplicate": "Duplicate Invoice Check",
}


def _check_entry(check_id, passed, fraud=False, reason="", skipped=False):
    return {
        "check": check_id,
        "label": CHECK_LABELS[check_id],
        "passed": passed,
        "fraud": fraud,
        "reason": reason,
        "skipped": skipped,
    }


def run_checks(extraction, ctx, history=None):
    """Run all validation rules. Returns (findings, checks) for decide + audit UI."""
    history = history or []
    findings = []
    checks = []
    amt = extraction.get("invoice_amount")
    items = extraction.get("line_items") or []

    vfind, vendor = resolve_vendor(extraction, ctx["vendors"])
    if vfind:
        findings.append(vfind)
        checks.append(_check_entry("vendor_name", False, vfind.fraud, vfind.reason))
    else:
        checks.append(_check_entry(
            "vendor_name", True,
            reason=f"Matched approved vendor '{vendor['vendor_name']}'",
        ))

    ref = (extraction.get("po_reference") or "").strip()
    po_match = None
    if not ref:
        reason = "No PO reference printed - nothing to match against"
        findings.append(Finding("po_missing", True, False, reason))
        checks.append(_check_entry("po_reference", False, False, reason))
        checks.append(_check_entry("po_amount", True, reason="Skipped — no PO reference", skipped=True))
        checks.append(_check_entry("po_qty", True, reason="Skipped — no PO reference", skipped=True))
    else:
        po_match = next((p for p in ctx["pos"] if p["po_number"].lower() == ref.lower()), None)
        if not po_match:
            reason = f"PO {ref} is not in the open purchase orders"
            findings.append(Finding("po_not_found", True, False, reason))
            checks.append(_check_entry("po_reference", False, False, reason))
            checks.append(_check_entry("po_amount", True, reason="Skipped — PO not on file", skipped=True))
            checks.append(_check_entry("po_qty", True, reason="Skipped — PO not on file", skipped=True))
        else:
            checks.append(_check_entry("po_reference", True, reason=f"PO {ref} found on file"))
            if amt is not None and not money_equal(amt, po_match["po_amount"]):
                reason = (
                    f"Invoice ${amt:,.0f} does not match PO {ref} "
                    f"(${po_match['po_amount']:,.0f})"
                )
                findings.append(Finding("po_amount_mismatch", True, False, reason))
                checks.append(_check_entry("po_amount", False, False, reason))
            else:
                checks.append(_check_entry(
                    "po_amount", True,
                    reason=f"Invoice amount matches PO (${po_match['po_amount']:,.0f})",
                ))
            if not items or po_match["recurring"]:
                skip_reason = (
                    "Skipped — recurring PO"
                    if po_match["recurring"]
                    else "Skipped — no line items"
                )
                checks.append(_check_entry("po_qty", True, reason=skip_reason, skipped=True))
            else:
                total_qty = sum((it.get("qty") or 0) for it in items)
                if total_qty and total_qty != po_match["auth_qty"]:
                    reason = (
                        f"Invoice quantity {total_qty:g} exceeds PO authorized "
                        f"quantity {po_match['auth_qty']:g}"
                    )
                    findings.append(Finding("po_qty_mismatch", True, False, reason))
                    checks.append(_check_entry("po_qty", False, False, reason))
                else:
                    checks.append(_check_entry(
                        "po_qty", True,
                        reason=f"Quantity {total_qty:g} within PO authorized {po_match['auth_qty']:g}",
                    ))

    math_findings = check_math(extraction)
    findings += math_findings
    if not items:
        checks.append(_check_entry("line_math", True, reason="Skipped — no line items", skipped=True))
        checks.append(_check_entry("total_math", True, reason="Skipped — no line items", skipped=True))
    else:
        line_fails = [f for f in math_findings if f.check == "line_math"]
        total_fails = [f for f in math_findings if f.check == "total_math"]
        if line_fails:
            checks.append(_check_entry(
                "line_math", False, False,
                "; ".join(f.reason for f in line_fails),
            ))
        else:
            checks.append(_check_entry(
                "line_math", True,
                reason="All line totals match qty × unit price",
            ))
        if total_fails:
            checks.append(_check_entry("total_math", False, False, total_fails[0].reason))
        elif amt is None:
            checks.append(_check_entry(
                "total_math", True, reason="Skipped — invoice total not read", skipped=True,
            ))
        else:
            checks.append(_check_entry(
                "total_math", True, reason="Line items sum matches invoice total",
            ))

    if not vendor:
        checks.append(_check_entry(
            "bank_account", True, reason="Skipped — vendor not verified", skipped=True,
        ))
        checks.append(_check_entry(
            "amount_anomaly", True, reason="Skipped — vendor not verified", skipped=True,
        ))
    else:
        bank_f = check_bank(extraction, vendor)
        findings += bank_f
        if bank_f:
            checks.append(_check_entry("bank_account", False, True, bank_f[0].reason))
        else:
            inv_bank = (extraction.get("bank_account_last4") or "").strip() or "—"
            checks.append(_check_entry(
                "bank_account", True,
                reason=f"Bank …{inv_bank} matches vendor master",
            ))

        anom_f = check_anomaly(extraction, vendor)
        findings += anom_f
        if anom_f:
            checks.append(_check_entry("amount_anomaly", False, True, anom_f[0].reason))
        else:
            checks.append(_check_entry(
                "amount_anomaly", True, reason="Amount within normal range for vendor",
            ))

    dup_f = check_duplicate(extraction, ctx, history)
    findings += dup_f
    if dup_f:
        checks.append(_check_entry("duplicate", False, True, dup_f[0].reason))
    else:
        checks.append(_check_entry("duplicate", True, reason="No duplicate payment detected"))

    return findings, checks
