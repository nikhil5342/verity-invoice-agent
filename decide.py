"""
GOVERNANCE: the decision layer.

Encodes the two-signal distinction from the thesis:
  - low read confidence            -> ESCALATE ("I'm not sure I read it")
  - read fine but a check failed   -> FLAG      ("I read it and found a problem")
  - read fine and all checks pass  -> AUTO-CLEAR
"""
from dataclasses import dataclass
from typing import List
import config


@dataclass
class Decision:
    decision: str          # AUTO-CLEAR | FLAG | ESCALATE
    confidence: float
    reasons: List[str]
    fraud_flag: str        # "Yes" | "No"


def decide(extraction, findings, threshold=None):
    threshold = config.CONFIDENCE_THRESHOLD if threshold is None else threshold
    confs = extraction.get("field_confidence") or {}
    min_conf = round(min(confs.values()), 2) if confs else 0.0

    # Can't reason about an amount we couldn't read.
    if extraction.get("invoice_amount") is None or min_conf < threshold:
        return Decision("ESCALATE", min_conf,
                        ["Low read confidence - a human should verify the scan"], "No")

    problems = [f for f in findings if f.failed]
    if problems:
        fraud = "Yes" if any(f.fraud for f in problems) else "No"
        return Decision("FLAG", min_conf, [f.reason for f in problems], fraud)

    return Decision("AUTO-CLEAR", min_conf, ["All checks passed"], "No")
