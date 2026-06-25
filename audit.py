"""GOVERNANCE: append-only audit trail. Every step of every invoice is logged."""
import json
import datetime
import config


def log(invoice_id, stage, payload):
    record = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "invoice_id": invoice_id,
        "stage": stage,          # e.g. "extract", "validate", "decide"
        "payload": payload,
    }
    with open(config.AUDIT_LOG, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def read_log(invoice_id=None):
    """Return all log records, optionally filtered to one invoice."""
    out = []
    try:
        with open(config.AUDIT_LOG) as f:
            for line in f:
                rec = json.loads(line)
                if invoice_id is None or rec["invoice_id"] == invoice_id:
                    out.append(rec)
    except FileNotFoundError:
        pass
    return out


def read_latest_run(invoice_id):
    """Return records for the most recent processing run of one invoice.

    A run begins at an ``extract`` stage and includes every later stage until
    the next ``extract`` for the same invoice (or end of log). Re-processing the
    same file appends a new run; the UI should show only the latest one.
    """
    records = read_log(invoice_id)
    if not records:
        return []

    last_extract = None
    for i in range(len(records) - 1, -1, -1):
        if records[i].get("stage") == "extract":
            last_extract = i
            break

    if last_extract is None:
        return records
    return records[last_extract:]
