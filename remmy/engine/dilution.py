"""New hire dilution system with ambassador conditional activation."""

import math

DILUTION_TIERS = [
    (0.10, 0.0, None),
    (0.21, 0.05, "warning"),
    (0.36, 0.10, "warning"),
    (1.01, 0.15, "critical"),
]


def get_dilution_factor(new_hire_pct: float) -> tuple[float, list]:
    """Returns (dilution_factor, flags) based on new hire %."""
    flags = []
    for threshold, factor, severity in DILUTION_TIERS:
        if new_hire_pct < threshold:
            if severity == "critical":
                flags.append({
                    "flag": "New Hire Dilution Risk", "severity": "critical",
                    "detail": f"New hire % is {new_hire_pct:.0%} (>35%). -15% UPH applied. OM review required.",
                })
            elif severity == "warning" and factor > 0:
                flags.append({
                    "flag": "New Hire Dilution", "severity": "warning",
                    "detail": f"New hire % is {new_hire_pct:.0%}. -{factor:.0%} UPH dilution applied.",
                })
            return factor, flags
    return 0.15, flags


def compute_ambassador_hc(new_hire_count: int) -> int:
    """Ambassador HC = ceil(new_hire_count / 10). 0 if no new hires."""
    if new_hire_count <= 0:
        return 0
    return math.ceil(new_hire_count / 10)


def check_dilution_resurface(role_code: str, planned_uph: float,
                             actual_uph: float, new_hire_prompted: bool) -> str | None:
    """If OM dismissed new hire prompt and rate outlier consistent with dilution, re-surface."""
    if new_hire_prompted:
        return None
    if planned_uph <= 0:
        return None
    deviation = (planned_uph - actual_uph) / planned_uph
    if deviation >= 0.05:
        return (f"Your {role_code} rate is tracking {deviation:.0%} below baseline. "
                "Did you have new hires today? I can apply dilution retroactively.")
    return None
