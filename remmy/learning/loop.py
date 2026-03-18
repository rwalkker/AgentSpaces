"""Learning loop — baseline updates, override patterns, metrics, phase regression."""

from datetime import datetime, timezone, timedelta
from remmy.db import get_session
from remmy.models import LearningMetric, ShiftPlan, ShiftActual, Override, RollingAverage

ACCURACY_TARGET = 0.95
OVERRIDE_FREQ_TARGET = 0.20
ACCEPTANCE_TARGET = 0.80
REGRESSION_FLOOR = 0.90
REGRESSION_CONSECUTIVE = 5
STALE_HOURS = 24


def update_baseline_on_close(plan_id: int):
    """When OM closes artifact, update rolling averages from actuals."""
    session = get_session()
    try:
        plan = session.query(ShiftPlan).get(plan_id)
        if not plan:
            return
        actuals = session.query(ShiftActual).filter_by(plan_id=plan_id).all()
        for actual in actuals:
            if actual.actual_uph and actual.actual_uph > 0:
                session.add(RollingAverage(
                    site=plan.site,
                    model="CRET" if actual.role_code.startswith("CRET") else "WHD",
                    role_code=actual.role_code,
                    week_date=plan.date,
                    actual_uph=actual.actual_uph,
                ))
        plan.closed_at = datetime.now(timezone.utc)
        session.commit()
    finally:
        session.close()


def compute_planning_accuracy(plan_id: int) -> float | None:
    """1 - |Planned - Actual| / Planned, averaged across roles."""
    session = get_session()
    try:
        plan = session.query(ShiftPlan).get(plan_id)
        if not plan or not plan.cret_direct_hc:
            return None
        actuals = {a.role_code: a.actual_hc for a in
                   session.query(ShiftActual).filter_by(plan_id=plan_id).all()
                   if a.actual_hc is not None}
        if not actuals:
            return None
        accuracies = []
        planned = plan.cret_direct_hc or {}
        for code, planned_hc in planned.items():
            if code in actuals and planned_hc > 0:
                acc = 1 - abs(planned_hc - actuals[code]) / planned_hc
                accuracies.append(max(acc, 0))
        return sum(accuracies) / len(accuracies) if accuracies else None
    finally:
        session.close()


def record_learning_metric(plan: ShiftPlan, accuracy: float):
    session = get_session()
    try:
        # Count overrides for this plan
        override_count = session.query(Override).filter_by(plan_id=plan.id).count()
        total_roles = len((plan.cret_direct_hc or {}).keys()) + len((plan.whd_direct_hc or {}).keys())
        override_freq = override_count / max(total_roles, 1)

        session.add(LearningMetric(
            site=plan.site,
            shift_date=plan.date,
            shift_type=plan.shift_type,
            planning_accuracy=accuracy,
            override_frequency=override_freq,
            recommendation_acceptance=1.0 - override_freq,
        ))
        session.commit()
    finally:
        session.close()


def check_phase_regression(site: str = "PHX6") -> tuple[int, list]:
    """Check if accuracy has dropped below 90% for 5 consecutive shifts → regress one phase."""
    session = get_session()
    flags = []
    try:
        recent = (session.query(LearningMetric)
                  .filter_by(site=site)
                  .order_by(LearningMetric.created_at.desc())
                  .limit(REGRESSION_CONSECUTIVE).all())
        if len(recent) < REGRESSION_CONSECUTIVE:
            return recent[0].phase if recent else 1, flags

        current_phase = recent[0].phase
        all_below = all(m.planning_accuracy < REGRESSION_FLOOR for m in recent)
        if all_below and current_phase > 1:
            new_phase = current_phase - 1
            flags.append({
                "flag": "Phase Regression", "severity": "critical",
                "detail": f"Accuracy <90% for {REGRESSION_CONSECUTIVE} consecutive shifts. "
                          f"Regressing from Phase {current_phase} to Phase {new_phase}.",
            })
            return new_phase, flags
        return current_phase, flags
    finally:
        session.close()


def check_baseline_stale(site: str = "PHX6") -> list[dict]:
    """Check if rolling avg hasn't been updated within 24 hours."""
    session = get_session()
    try:
        latest = (session.query(RollingAverage)
                  .filter_by(site=site)
                  .order_by(RollingAverage.created_at.desc())
                  .first())
        if latest and latest.created_at:
            age = datetime.now(timezone.utc) - latest.created_at.replace(tzinfo=timezone.utc)
            if age > timedelta(hours=STALE_HOURS):
                return [{"flag": "Baseline Stale", "severity": "warning",
                         "detail": f"Rolling average last updated {age.total_seconds() / 3600:.0f}h ago. Close artifact to update."}]
        return []
    finally:
        session.close()


def check_override_anomaly(site: str = "PHX6") -> list[dict]:
    """Check if override patterns correlate with negative outcomes."""
    session = get_session()
    try:
        # Get recent plans with overrides and their accuracy
        recent = (session.query(LearningMetric)
                  .filter_by(site=site)
                  .order_by(LearningMetric.created_at.desc())
                  .limit(10).all())
        overridden = [m for m in recent if m.override_frequency > 0]
        if len(overridden) < 3:
            return []
        avg_acc = sum(m.planning_accuracy for m in overridden) / len(overridden)
        if avg_acc < ACCURACY_TARGET:
            return [{"flag": "Override Anomaly", "severity": "warning",
                     "detail": f"Override patterns correlating with lower accuracy ({avg_acc:.1%}). Not adopted as default."}]
        return []
    finally:
        session.close()


def generate_weekly_summary(site: str = "PHX6") -> str:
    session = get_session()
    try:
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        metrics = (session.query(LearningMetric)
                   .filter(LearningMetric.site == site,
                           LearningMetric.created_at >= week_ago)
                   .all())
        if not metrics:
            return "No shift data from the past week to summarize."

        avg_acc = sum(m.planning_accuracy for m in metrics) / len(metrics)
        avg_override = sum(m.override_frequency for m in metrics) / len(metrics)
        avg_accept = sum(m.recommendation_acceptance for m in metrics) / len(metrics)
        current_phase = metrics[-1].phase

        lines = [
            "═══ WEEKLY LEARNING SUMMARY ═══",
            f"  Shifts Analyzed: {len(metrics)}",
            f"  Planning Accuracy: {avg_acc:.1%} (target: >95%)",
            f"  Override Frequency: {avg_override:.1%} (target: <20%)",
            f"  Recommendation Acceptance: {avg_accept:.1%} (target: >80%)",
            f"  Current Phase: {current_phase}",
            "═══════════════════════════════",
        ]
        return "\n".join(lines)
    finally:
        session.close()
