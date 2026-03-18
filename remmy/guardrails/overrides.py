"""Override system with cascade recalculation and conflict resolution."""

from datetime import datetime, timezone
from remmy.db import get_session
from remmy.models import Override

# Conflict resolution priority (highest first)
PRIORITY_ORDER = [
    "actual_attendance",
    "ps_anchor",
    "support_ceiling",
    "om_override",
    "calculated",
]

SOFT_THRESHOLD = 0.20  # ±20%


def classify_override(original: float, new_value: float) -> str:
    if original == 0:
        return "hard"
    deviation = abs(new_value - original) / original
    return "soft" if deviation <= SOFT_THRESHOLD else "hard"


def apply_override(plan_id: int, role_code: str, original: float,
                   new_value: float, justification: str = "",
                   force_lock: bool = False) -> tuple[dict, list]:
    """Apply an override. Returns (override_record, flags)."""
    flags = []
    override_type = "lock" if force_lock else classify_override(original, new_value)

    if override_type == "hard" and not justification:
        flags.append({
            "flag": "Override Requires Justification", "severity": "critical",
            "detail": f"{role_code}: Override from {original} to {new_value} is >{SOFT_THRESHOLD:.0%}. One-line justification required.",
        })
        return {}, flags

    record = {
        "plan_id": plan_id,
        "role_code": role_code,
        "original_value": original,
        "override_value": new_value,
        "justification": justification,
        "override_type": override_type,
        "timestamp": datetime.now(timezone.utc),
    }

    # Persist
    session = get_session()
    try:
        session.add(Override(**record))
        session.commit()
    finally:
        session.close()

    return record, flags


def get_override_history(plan_id: int) -> list[dict]:
    session = get_session()
    try:
        rows = session.query(Override).filter_by(plan_id=plan_id).order_by(Override.timestamp).all()
        return [{
            "timestamp": r.timestamp.isoformat() if r.timestamp else "",
            "role_code": r.role_code,
            "original": r.original_value,
            "override": r.override_value,
            "justification": r.justification or "",
            "type": r.override_type,
        } for r in rows]
    finally:
        session.close()


def resolve_conflict(values: list[tuple[str, float]]) -> tuple[float, str]:
    """Given list of (priority_source, value), return winning value and source.
    priority_source must be one of PRIORITY_ORDER."""
    best_priority = len(PRIORITY_ORDER)
    best_value = 0.0
    best_source = "calculated"
    for source, value in values:
        idx = PRIORITY_ORDER.index(source) if source in PRIORITY_ORDER else len(PRIORITY_ORDER)
        if idx < best_priority:
            best_priority = idx
            best_value = value
            best_source = source
    return best_value, best_source


def check_cascade_conflict(locked_roles: dict[str, float],
                           recalculated: dict[str, float]) -> list[dict]:
    """Check if locked values conflict with recalculated downstream values."""
    flags = []
    for code, locked_val in locked_roles.items():
        if code in recalculated and recalculated[code] != locked_val:
            flags.append({
                "flag": "Lock Cascade Warning", "severity": "warning",
                "detail": f"🔒 {code} locked at {locked_val} but recalculation suggests {recalculated[code]}.",
            })
    return flags
