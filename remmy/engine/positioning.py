"""Positioning strategy engine: On Course / Underprocess / Overprocess."""

from dataclasses import dataclass


@dataclass
class PositioningResult:
    strategy: str  # "on_course" / "underprocess" / "overprocess"
    label: str
    adjustment: float  # percentage
    flags: list


def determine_positioning(backlog_current: float, backlog_target: float,
                          prior_shift_result: str,
                          requested_strategy: str | None = None) -> PositioningResult:
    """
    Determine positioning based on backlog and prior shift.
    prior_shift_result: "hit" / "miss" / "exceed"
    requested_strategy: optional OM override request
    """
    flags = []
    backlog_diff_pct = 0.0
    if backlog_target > 0:
        backlog_diff_pct = (backlog_current - backlog_target) / backlog_target

    backlog_above = backlog_diff_pct > 0.05
    backlog_below = backlog_diff_pct < -0.05
    backlog_on = not backlog_above and not backlog_below
    prior_missed = prior_shift_result == "miss"
    prior_hit_or_exceed = prior_shift_result in ("hit", "exceed")

    # Error 2.1: Overprocess requested when backlog above target
    if requested_strategy == "overprocess" and backlog_above:
        flags.append({
            "flag": "Overprocess Ceiling", "severity": "critical",
            "detail": "Overprocess requested but backlog is ABOVE target. "
                      "Correct strategy is Underprocess. Recommending Underprocess (-10%).",
        })
        return PositioningResult("underprocess", "🔽 Underprocess", -10.0, flags)

    # Determine natural strategy
    if backlog_above or prior_missed:
        # Edge case: backlog on target but prior missed → underprocess
        if backlog_on and prior_missed:
            adj = -5.0
        else:
            adj = -10.0 if backlog_above else -5.0
        return PositioningResult("underprocess", "🔽 Underprocess", adj, flags)

    if backlog_below and prior_hit_or_exceed:
        # Determine overprocess magnitude
        magnitude = abs(backlog_diff_pct) * 100
        if magnitude <= 15:
            adj = min(magnitude, 15.0)
        elif magnitude <= 20:
            adj = min(magnitude, 20.0)
            flags.append({
                "flag": "Overprocess Warning", "severity": "warning",
                "detail": f"Overprocess adjustment +{adj:.0f}% is in 16-20% range. One-line justification required.",
            })
        else:
            flags.append({
                "flag": "Overprocess Ceiling", "severity": "critical",
                "detail": f"Overprocess adjustment would be +{magnitude:.0f}% (>20%). Hard Stop — explicit justification + risk acknowledgment required.",
            })
            adj = 20.0  # cap at ceiling
        return PositioningResult("overprocess", "🔼 Overprocess", adj, flags)

    # On course
    return PositioningResult("on_course", "✅ On Course", 0.0, flags)
