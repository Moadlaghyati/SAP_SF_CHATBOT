from __future__ import annotations

import re

from app.agents.sap.absence_schemas import AbsenceIntentResult


ABSENCE_PATTERNS: tuple[tuple[str, float], ...] = (
    (r"\babsences?\b", 0.95),
    (r"\babsent\b", 0.95),
    (r"\bleaves?\b", 0.9),
    (r"\btime\s*off\b", 0.95),
    (r"\bpto\b", 0.95),
    (r"\bvacations?\b", 0.9),
    (r"\bholidays?\b", 0.75),
    (r"\bsick\s+leave\b", 0.98),
    (r"\bdays?\s+off\b", 0.9),
    (r"\bwho\s+is\s+absent\b", 0.98),
    (r"\bshow\s+me\s+absences?\b", 0.98),
    (r"\bget\s+employee\s+leave\b", 0.98),
)


def detect_absence_intent(message: str) -> AbsenceIntentResult:
    text = message.strip().lower()
    if not text:
        return AbsenceIntentResult(False, "Empty message.", 0.0)

    best_confidence = 0.0
    best_pattern = None
    for pattern, confidence in ABSENCE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            if confidence > best_confidence:
                best_confidence = confidence
                best_pattern = pattern

    if best_pattern is None:
        return AbsenceIntentResult(False, "No absence-related trigger was found.", 0.0)

    return AbsenceIntentResult(
        True,
        f"Matched absence-related trigger: {best_pattern}",
        best_confidence,
    )
