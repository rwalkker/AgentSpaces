"""v1.2/v1.3 addenda — indirect ratio cross-check, EOS quality, PS escalation."""

from remmy.engine.roles import INDIRECT_RATIOS
from remmy.guardrails.flags import check_indirect_ratio_deviation, check_eos_quality

# Permissions matrix (informational)
PERMISSIONS = {
    "CRET Processor": {"group": "C-Returns (Sub)", "level": "Beginner: Customer Returns App, Kindle CRET UI"},
    "CRET Support/Indirect": {"group": "C-Returns Support",
                              "level": "Beginner: Sort, Audit, Move, Unloader; Intermediate: Ambassador, PS, Lead/PA"},
}

# 50% rotation rule
ROTATION_RULE = "No associate may spend more than 50% of weekly hours in an indirect path."


def cross_check_indirect_ratios(direct_hc: int, indirect_hc_map: dict[str, int]) -> list[dict]:
    """Cross-check indirect HC against v1.3 policy ratios at finalization."""
    flags = []
    for calm_code, (name, policy_ratio) in INDIRECT_RATIOS.items():
        if calm_code in indirect_hc_map and direct_hc > 0:
            actual_ratio = indirect_hc_map[calm_code] / direct_hc
            flags.extend(check_indirect_ratio_deviation(calm_code, actual_ratio, policy_ratio))
    return flags


def check_ps_escalation_rate(escalated_lpns: int, total_lpns: int) -> list[dict]:
    """Check PS escalation rate against 4.89% target."""
    if total_lpns <= 0:
        return []
    rate = escalated_lpns / total_lpns
    if rate >= 0.0489:
        return [{"flag": "PS Escalation Warning", "severity": "warning",
                 "detail": f"PS Escalation Rate {rate:.2%} exceeds 4.89% target. Flag for OM floor walk."}]
    if rate >= 0.04:
        return [{"flag": "PS Escalation Warning", "severity": "warning",
                 "detail": f"PS Escalation Rate {rate:.2%} approaching 4.89% target."}]
    return []
