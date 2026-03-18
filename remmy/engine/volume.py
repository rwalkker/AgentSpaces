"""Volume engine: Big Gulp → shift volume → role volume breakdown."""

from remmy.engine.roles import (
    CRET_DIRECT, Quarter, adjusted_uph, WHD_DIRECT, WHD_VOLUME_SPLIT,
)

# AR/WHD yield rate from CRET processed volume
WHD_YIELD_RATE = 0.03

# Half-shift distribution
FIRST_HALF_VOL_PCT = 0.479
SECOND_HALF_VOL_PCT = 0.521
FIRST_HALF_HC_MULT = 0.92
SECOND_HALF_HC_MULT = 1.08


def compute_day_night_split(day_hc: float, night_hc: float,
                            day_show_rate: float, night_show_rate: float,
                            shift_duration: float) -> tuple[float, float]:
    """Returns (day_volume_pct, night_volume_pct) based on show hours ratio."""
    day_show = day_hc * day_show_rate * shift_duration
    night_show = night_hc * night_show_rate * shift_duration
    total = day_show + night_show
    if total == 0:
        return 0.5, 0.5
    return day_show / total, night_show / total


def convergence_check(seed_hc: float, final_hc: float) -> bool:
    """Returns True if final HC deviates >10% from seed — needs recalculation offer."""
    if seed_hc == 0:
        return False
    return abs(final_hc - seed_hc) / seed_hc > 0.10


def compute_cret_role_volumes(shift_volume: float, ns_pct: float | None = None) -> dict[str, float]:
    """Break shift volume into per-role volumes using PHX6 default allocations."""
    result = {}
    for role in CRET_DIRECT:
        result[role.code] = shift_volume * role.volume_pct
    return result


def compute_whd_volume(cret_processed_volume: float) -> float:
    return cret_processed_volume * WHD_YIELD_RATE


def compute_whd_role_volumes(whd_volume: float) -> dict[str, float]:
    return {code: whd_volume * pct for code, pct in WHD_VOLUME_SPLIT.items()}


def get_adjusted_uph_map(roles: list, quarter: Quarter,
                         rolling_avgs: dict[str, float] | None = None,
                         dilution_factor: float = 0.0) -> dict[str, float]:
    """Get adjusted UPH for each role. Uses rolling avg if available, else baseline."""
    result = {}
    for role in roles:
        base = rolling_avgs.get(role.code, role.baseline_uph) if rolling_avgs else role.baseline_uph
        uph = adjusted_uph(base, quarter)
        if dilution_factor > 0:
            uph *= (1 - dilution_factor)
        result[role.code] = round(uph, 1)
    return result
