from __future__ import annotations
"""Risk engine: turns raw model output into business decisions.

Inputs  : deepfake probability (0..1), identity match (0-100 or None), input quality (0-100)
Outputs : Deepfake Risk Score, Trust Score, classification and human-readable reasons.
The model never decides alone - rules below are explicit, explainable and tunable in config.py.
"""
from collections import deque
from dataclasses import dataclass, field


@dataclass
class RiskResult:
    risk_score: float          # Deepfake Risk Score 0-100
    trust_score: float         # 0-100
    result: str                # Approved / Suspicious / Rejected
    severity: str | None       # None / Warning / High / Critical  (alert level)
    reasons: list = field(default_factory=list)


def evaluate(deepfake_prob, identity_match, quality, faces_found, cfg, identity_required=False):
    reasons = []
    risk = round(100 * deepfake_prob, 1)

    # Trust combines three signals (literature review, section 3.4):
    # "is it manipulated?" + "is it the person they claim to be?" + "can we trust the input?"
    if identity_match is None:
        trust = 100 - risk
    else:
        trust = 0.6 * (100 - risk) + 0.4 * identity_match
    trust = round(trust * (0.7 + 0.3 * quality / 100), 1)   # poor input lowers confidence

    if not faces_found:
        return RiskResult(risk, 0.0, "Suspicious", "Warning",
                          ["No face detected - identity could not be verified"])

    result = "Approved"
    if risk >= cfg["RISK_REJECTED"]:
        result = "Rejected"
        reasons.append(f"High deepfake probability ({risk:.0f}%)")
    elif risk >= cfg["RISK_SUSPICIOUS"]:
        result = "Suspicious"
        reasons.append(f"Elevated deepfake probability ({risk:.0f}%)")

    if identity_match is not None:
        if identity_match < cfg["IDENTITY_REJECT"]:
            result = "Rejected"
            reasons.append(f"Face does not match the claimed identity ({identity_match:.0f}%)")
        elif identity_match < cfg["IDENTITY_OK"] and result == "Approved":
            result = "Suspicious"
            reasons.append(f"Weak match to the claimed identity ({identity_match:.0f}%)")

    elif identity_required and result == "Approved":
        result = "Suspicious"
        reasons.append("Face too small or unclear to verify the claimed identity")

    if quality < cfg["QUALITY_MIN"] and result == "Approved":
        result = "Suspicious"
        reasons.append(f"Low video quality ({quality:.0f}/100) - result not reliable")

    severity = {"Approved": None, "Suspicious": "Warning", "Rejected": "High"}[result]
    if result == "Rejected" and (risk >= cfg["RISK_CRITICAL"] or
                                 (identity_match is not None and identity_match < cfg["IDENTITY_REJECT"]
                                  and risk >= cfg["RISK_SUSPICIOUS"])):
        severity = "Critical"
    if not reasons:
        reasons.append("No indicators of manipulation")
    return RiskResult(risk, trust, result, severity, reasons)


class Smoother:
    """Moving average over the last N frame scores so a single noisy frame
    (e.g. 20%, 25%, 87%, 22%) does not trigger an alert on its own."""

    def __init__(self, size):
        self.values = deque(maxlen=size)

    def add(self, value):
        self.values.append(value)
        return sum(self.values) / len(self.values)
