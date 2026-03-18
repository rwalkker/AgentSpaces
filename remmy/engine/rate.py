"""4-week rolling average with anomaly detection and NS% auto-application."""

from remmy.db import get_session
from remmy.models import RollingAverage, NsRollingAverage

ANOMALY_THRESHOLD = 0.25
MAX_CONSECUTIVE_ANOMALIES = 2


def get_rolling_average(role_code: str, model: str = "CRET",
                        site: str = "PHX6") -> tuple[float | None, list]:
    """Returns (rolling_avg_uph, flags). Uses last 4 weeks, with anomaly exclusion."""
    session = get_session()
    flags = []
    try:
        rows = (session.query(RollingAverage)
                .filter_by(site=site, model=model, role_code=role_code)
                .order_by(RollingAverage.week_date.desc())
                .limit(8).all())  # fetch extra for replacement
        if len(rows) < 4:
            return None, flags

        # Build 4-week window with anomaly handling
        values = [r.actual_uph for r in rows]
        window = []
        consecutive_anomalies = 0
        base_avg = sum(values[:4]) / 4  # initial estimate

        for i, val in enumerate(values):
            if len(window) >= 4:
                break
            deviation = abs(val - base_avg) / base_avg if base_avg > 0 else 0
            if deviation > ANOMALY_THRESHOLD:
                consecutive_anomalies += 1
                if consecutive_anomalies > MAX_CONSECUTIVE_ANOMALIES:
                    flags.append({
                        "flag": "Data Confidence", "severity": "critical",
                        "detail": f"{role_code}: {consecutive_anomalies} consecutive anomalous weeks. Manual UPH baseline required.",
                    })
                    return None, flags
                # Skip anomaly, will use next available value
                rows[i].is_anomaly = True
                continue
            else:
                consecutive_anomalies = 0
                window.append(val)

        if len(window) < 4:
            return None, flags

        session.commit()
        return sum(window) / len(window), flags
    finally:
        session.close()


def get_all_rolling_averages(model: str = "CRET", site: str = "PHX6") -> tuple[dict[str, float], list]:
    """Get rolling averages for all roles in a model. Returns (avg_map, flags)."""
    from remmy.engine.roles import CRET_DIRECT, WHD_DIRECT
    roles = CRET_DIRECT if model == "CRET" else WHD_DIRECT
    avg_map = {}
    all_flags = []
    for role in roles:
        avg, flags = get_rolling_average(role.code, model, site)
        if avg is not None:
            avg_map[role.code] = avg
        all_flags.extend(flags)
    return avg_map, all_flags


def get_ns_rolling_average(site: str = "PHX6") -> tuple[float | None, list]:
    """Get 4-week rolling NS% average."""
    session = get_session()
    flags = []
    try:
        rows = (session.query(NsRollingAverage)
                .filter_by(site=site)
                .order_by(NsRollingAverage.week_date.desc())
                .limit(4).all())
        if len(rows) < 4:
            return None, flags
        avg = sum(r.ns_pct for r in rows) / len(rows)
        if avg > 0.50:
            flags.append({
                "flag": "High Non-Sort Volume", "severity": "warning",
                "detail": f"4-week rolling NS% is {avg:.1%} (>50%). OM awareness required.",
            })
        return avg, flags
    finally:
        session.close()


def record_weekly_uph(role_code: str, week_date: str, actual_uph: float,
                      model: str = "CRET", site: str = "PHX6"):
    session = get_session()
    try:
        session.add(RollingAverage(
            site=site, model=model, role_code=role_code,
            week_date=week_date, actual_uph=actual_uph,
        ))
        session.commit()
    finally:
        session.close()
