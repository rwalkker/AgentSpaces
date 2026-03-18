"""HC calculation engine — CRET 16-role + AR/WHD 3-role models."""

import math
from dataclasses import dataclass, field
from remmy.engine.roles import CRET_DIRECT, CRET_SUPPORT, WHD_DIRECT, Quarter
from remmy.engine.volume import (
    compute_cret_role_volumes, compute_whd_volume, compute_whd_role_volumes,
    get_adjusted_uph_map,
)

SUPPORT_BUDGET_PCT = 0.0647
PS_ANCHOR_RATIO = 40
FHN_CEILING = 0.192
ROUNDING_OVERAGE_CEILING = 0.08
WHD_INDIRECT_PCT = 0.08


@dataclass
class HCResult:
    cret_direct: dict[str, int] = field(default_factory=dict)
    cret_support: dict[str, int] = field(default_factory=dict)
    total_direct_hc: int = 0
    total_support_hc: int = 0
    total_cret_hc: int = 0
    support_pct: float = 0.0
    whd_direct: dict[str, int] = field(default_factory=dict)
    whd_indirect_buffer: int = 0
    total_whd_direct: int = 0
    total_whd_hc: int = 0
    building_total: int = 0
    flags: list = field(default_factory=list)
    # Intermediate values for artifact
    cret_role_volumes: dict[str, float] = field(default_factory=dict)
    whd_role_volumes: dict[str, float] = field(default_factory=dict)
    cret_uph_map: dict[str, float] = field(default_factory=dict)
    whd_uph_map: dict[str, float] = field(default_factory=dict)
    ambassador_hc: int = 0


def compute_role_hc(volume: float, uph: float, duration: float) -> int:
    if uph <= 0 or duration <= 0:
        return 0
    return math.ceil(volume / (uph * duration))


def compute_cret_support(total_direct: int, new_hire_count: int = 0,
                         overrides: dict[str, int] | None = None,
                         locks: set[str] | None = None) -> tuple[dict[str, int], int, list]:
    """8-step downstream recalculation sequence for CRET support."""
    overrides = overrides or {}
    locks = locks or set()
    flags = []

    # Step 1: Total Direct HC (input)
    # Step 2: Total Support Budget
    budget = math.ceil(total_direct * SUPPORT_BUDGET_PCT)
    # Step 3: PS HC (priority)
    ps_hc = math.ceil(total_direct / PS_ANCHOR_RATIO) if total_direct > 0 else 0
    if "CRET-PS" in overrides and "CRET-PS" in locks:
        ps_hc = overrides["CRET-PS"]
    elif "CRET-PS" in overrides:
        ps_hc = overrides["CRET-PS"]

    # Step 4: Remaining budget
    remaining = max(budget - ps_hc, 0)

    # Step 5: Ambassador (conditional) + 4 or 5 remaining roles
    ambassador_hc = 0
    non_ps_roles = [r.code for r in CRET_SUPPORT if r.code != "CRET-PS"]
    if new_hire_count > 0:
        ambassador_hc = math.ceil(new_hire_count / 10)
        # Ambassador takes from the budget; remaining 4 roles split the rest
        remaining_after_amb = max(remaining - ambassador_hc, 0)
        split_roles = [c for c in non_ps_roles if c != "CRET-LEAD"]
        # Use CRET-LEAD slot for ambassador
        per_role = math.ceil(remaining_after_amb / len(split_roles)) if split_roles else 0
        per_role = max(per_role, 1)
        support = {"CRET-PS": ps_hc}
        for code in split_roles:
            if code in locks and code in overrides:
                support[code] = overrides[code]
            elif code in overrides:
                support[code] = overrides[code]
            else:
                support[code] = per_role
        support["CRET-LEAD"] = ambassador_hc  # Ambassador replaces Lead slot
    else:
        per_role = math.ceil(remaining / len(non_ps_roles)) if non_ps_roles else 0
        per_role = max(per_role, 1) if remaining > 0 else 0
        support = {"CRET-PS": ps_hc}
        for code in non_ps_roles:
            if code in locks and code in overrides:
                support[code] = overrides[code]
            elif code in overrides:
                support[code] = overrides[code]
            else:
                support[code] = per_role

    # Step 6: Total CRET HC computed by caller
    total_support = sum(support.values())

    # Step 7: Support % validation
    total_hc = total_direct + total_support
    support_pct = total_support / total_hc if total_hc > 0 else 0

    # Rounding overage check
    if total_direct > 0:
        raw_pct = total_support / total_direct
        if raw_pct > ROUNDING_OVERAGE_CEILING:
            # Reduce one non-PS, non-ambassador role by 1
            for code in non_ps_roles:
                if code == "CRET-LEAD" and new_hire_count > 0:
                    continue  # don't reduce ambassador
                if code not in locks and support.get(code, 0) > 1:
                    support[code] -= 1
                    total_support = sum(support.values())
                    flags.append({
                        "flag": "Rounding Overage", "severity": "warning",
                        "detail": f"Support % exceeded 8.0% from rounding. Reduced {code} by 1 HC.",
                    })
                    break

    # Step 8: Escalation check
    total_hc = total_direct + total_support
    support_pct = total_support / total_hc if total_hc > 0 else 0
    if support_pct > FHN_CEILING:
        flags.append({
            "flag": "Support Overload", "severity": "critical",
            "detail": f"Support % {support_pct:.1%} exceeds 19.2% FHN ceiling. Review required.",
        })

    return support, ambassador_hc, flags


def compute_whd_hc(cret_processed_volume: float, shift_duration: float,
                   quarter: Quarter, rolling_avgs: dict[str, float] | None = None,
                   dilution_factor: float = 0.0) -> tuple[dict[str, int], int, dict[str, float], dict[str, float]]:
    """Compute AR/WHD direct HC + indirect buffer."""
    whd_volume = compute_whd_volume(cret_processed_volume)
    role_volumes = compute_whd_role_volumes(whd_volume)
    uph_map = get_adjusted_uph_map(WHD_DIRECT, quarter, rolling_avgs, dilution_factor)

    direct_hc = {}
    for role in WHD_DIRECT:
        vol = role_volumes[role.code]
        direct_hc[role.code] = compute_role_hc(vol, uph_map[role.code], shift_duration)

    total_direct = sum(direct_hc.values())
    indirect_buffer = math.floor(total_direct * WHD_INDIRECT_PCT)  # floor rounding

    return direct_hc, indirect_buffer, role_volumes, uph_map


def compute_full_plan(shift_volume: float, shift_duration: float, quarter: Quarter,
                      ns_pct: float = 0.0, new_hire_pct: float = 0.0,
                      new_hire_count: int = 0, dilution_factor: float = 0.0,
                      cret_rolling: dict[str, float] | None = None,
                      whd_rolling: dict[str, float] | None = None,
                      overrides: dict[str, int] | None = None,
                      locks: set[str] | None = None,
                      positioning_adj: float = 0.0) -> HCResult:
    """Full plan computation: CRET + AR/WHD."""
    result = HCResult()

    # Apply positioning adjustment to volume
    adj_volume = shift_volume * (1 + positioning_adj / 100)

    # CRET role volumes
    result.cret_role_volumes = compute_cret_role_volumes(adj_volume, ns_pct)
    result.cret_uph_map = get_adjusted_uph_map(CRET_DIRECT, quarter, cret_rolling, dilution_factor)

    # CRET direct HC
    for role in CRET_DIRECT:
        vol = result.cret_role_volumes[role.code]
        result.cret_direct[role.code] = compute_role_hc(vol, result.cret_uph_map[role.code], shift_duration)

    result.total_direct_hc = sum(result.cret_direct.values())

    # Apply overrides to direct roles
    if overrides:
        for code, val in overrides.items():
            if code in result.cret_direct:
                result.cret_direct[code] = val
        result.total_direct_hc = sum(result.cret_direct.values())

    # CRET support (8-step sequence)
    result.cret_support, result.ambassador_hc, support_flags = compute_cret_support(
        result.total_direct_hc, new_hire_count, overrides, locks
    )
    result.flags.extend(support_flags)
    result.total_support_hc = sum(result.cret_support.values())
    result.total_cret_hc = result.total_direct_hc + result.total_support_hc
    total = result.total_cret_hc
    result.support_pct = result.total_support_hc / total if total > 0 else 0

    # AR/WHD
    cret_processed = adj_volume  # CRET processed volume = shift volume after positioning
    result.whd_direct, result.whd_indirect_buffer, result.whd_role_volumes, result.whd_uph_map = compute_whd_hc(
        cret_processed, shift_duration, quarter, whd_rolling, dilution_factor
    )
    result.total_whd_direct = sum(result.whd_direct.values())
    result.total_whd_hc = result.total_whd_direct + result.whd_indirect_buffer

    result.building_total = result.total_cret_hc + result.total_whd_hc
    return result
