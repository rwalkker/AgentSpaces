"""Master Flag Reference Table — all flags from v1.1 + v1.3."""


# Severity tiers
CRITICAL = "critical"  # 🔴 blocks finalization
WARNING = "warning"    # 🟡 requires acknowledgment
INFO = "info"          # ℹ️ awareness only

SEVERITY_SYMBOLS = {CRITICAL: "🔴", WARNING: "🟡", INFO: "ℹ️"}

# RACI routing
RACI_ROUTING = {
    CRITICAL: "OM required",
    WARNING: "AM/PA awareness",
    INFO: "No escalation required",
}

# Master flag definitions
FLAG_DEFS = {
    "Support Overload": {"severity": CRITICAL, "trigger": "CRET support % >19.2%"},
    "Rate Outlier Warning": {"severity": WARNING, "trigger": "Role UPH >25% from 4-week avg"},
    "Rate Outlier Critical": {"severity": CRITICAL, "trigger": "Role UPH >50% from 4-week avg"},
    "New Hire Dilution Risk": {"severity": CRITICAL, "trigger": "New hire % >35%"},
    "Overprocess Ceiling": {"severity": CRITICAL, "trigger": "Positioning adj >+20%"},
    "Overprocess Warning": {"severity": WARNING, "trigger": "Positioning adj +16-20%"},
    "Volume Split Imbalance": {"severity": WARNING, "trigger": "Day/Night split >15% from 4-week avg"},
    "Rounding Overage": {"severity": WARNING, "trigger": "Support % >8.0% from rounding"},
    "High Non-Sort Volume": {"severity": WARNING, "trigger": "4-week rolling NS% >50%"},
    "Data Confidence": {"severity": CRITICAL, "trigger": "3+ consecutive anomalous weeks"},
    "Low Show Rate": {"severity": WARNING, "trigger": "Show rate 30-49%"},
    "Backlog Drift": {"severity": WARNING, "trigger": "Projected EOW backlog >10% from target"},
    "Override Anomaly": {"severity": WARNING, "trigger": "Override pattern correlates with negative outcomes"},
    "Baseline Stale": {"severity": WARNING, "trigger": "Rolling avg not updated within 24hrs"},
    "Q1 Active": {"severity": INFO, "trigger": "Q1 rate adjustments (+1.9%) in use"},
    "NS% Applied": {"severity": INFO, "trigger": "NS% auto-applied from rolling avg"},
    # v1.3 additions
    "Indirect Ratio Deviation": {"severity": WARNING, "trigger": "Indirect role HC >20% from policy ratio"},
    "Takt Risk": {"severity": WARNING, "trigger": "Takt Risk >0 at EOS"},
    "Quality Gap": {"severity": WARNING, "trigger": "Quality Engagements <10 per shift at EOS"},
    "Mastermind Backlog": {"severity": WARNING, "trigger": "Masterminds >0 pending at EOS"},
    "PS Escalation Warning": {"severity": WARNING, "trigger": "PS Escalation Rate approaching 4.89%"},
    "Inferred Time Outlier": {"severity": WARNING, "trigger": "Inferred Time % > site 4-week avg"},
    "Cycle Time Outlier": {"severity": WARNING, "trigger": "Cycle Time > site 4-week avg"},
    "New Hire Dilution": {"severity": WARNING, "trigger": "New hire % 10-35%"},
    "Process Loss Outlier": {"severity": WARNING, "trigger": "Total Process Loss % > site 4-week avg"},
}


def format_flag(flag: dict) -> str:
    sym = SEVERITY_SYMBOLS.get(flag["severity"], "❓")
    routing = RACI_ROUTING.get(flag["severity"], "")
    return f"{sym} {flag['flag']} — {flag['detail']} [{routing}]"


def blocks_finalization(flags: list[dict]) -> bool:
    return any(f["severity"] == CRITICAL for f in flags)


def get_unacknowledged_warnings(flags: list[dict], acknowledged: set[str]) -> list[dict]:
    return [f for f in flags if f["severity"] == WARNING and f["flag"] not in acknowledged]


def check_show_rate(rate: float) -> list[dict]:
    flags = []
    if rate < 0.30:
        flags.append({
            "flag": "Low Show Rate", "severity": CRITICAL,
            "detail": f"Show rate {rate:.0%} is below 30%. Likely data entry error. Please verify.",
        })
    elif rate < 0.50:
        flags.append({
            "flag": "Low Show Rate", "severity": WARNING,
            "detail": f"Show rate {rate:.0%} is between 30-49%. Possible mass call-out or data error.",
        })
    return flags


def check_rate_outlier(role_code: str, planned_uph: float, avg_uph: float) -> list[dict]:
    if avg_uph <= 0:
        return []
    deviation = abs(planned_uph - avg_uph) / avg_uph
    if deviation > 0.50:
        return [{"flag": "Rate Outlier Critical", "severity": CRITICAL,
                 "detail": f"{role_code} UPH deviation {deviation:.0%} from 4-week avg. Hard justification required."}]
    if deviation > 0.25:
        return [{"flag": "Rate Outlier Warning", "severity": WARNING,
                 "detail": f"{role_code} UPH deviation {deviation:.0%} from 4-week avg. Confirm data."}]
    return []


def check_volume_split_imbalance(day_pct: float, historical_day_pct: float | None) -> list[dict]:
    if historical_day_pct is None:
        return []
    if abs(day_pct - historical_day_pct) > 0.15:
        return [{"flag": "Volume Split Imbalance", "severity": WARNING,
                 "detail": f"Day split {day_pct:.1%} deviates >15% from 4-week avg {historical_day_pct:.1%}."}]
    return []


def check_indirect_ratio_deviation(role_calm: str, actual_ratio: float,
                                   policy_ratio: float) -> list[dict]:
    if policy_ratio <= 0:
        return []
    deviation = abs(actual_ratio - policy_ratio) / policy_ratio
    if deviation > 0.20:
        return [{"flag": "Indirect Ratio Deviation", "severity": WARNING,
                 "detail": f"{role_calm}: actual ratio {actual_ratio:.4f} vs policy {policy_ratio:.4f} (>{deviation:.0%} deviation)."}]
    return []


def check_eos_quality(takt_risk: int = 0, quality_engagements: int = 10,
                      masterminds_pending: int = 0, inferred_time_pct: float = 0,
                      site_inferred_avg: float = 0, cycle_time: float = 0,
                      site_cycle_avg: float = 0, process_loss_pct: float = 0,
                      site_loss_avg: float = 0) -> list[dict]:
    flags = []
    if takt_risk > 0:
        flags.append({"flag": "Takt Risk", "severity": WARNING,
                      "detail": f"{takt_risk} items processed in ≤10 seconds. Engage associate."})
    if quality_engagements < 10:
        flags.append({"flag": "Quality Gap", "severity": WARNING,
                      "detail": f"Only {quality_engagements} quality engagements (target: 10). Escalate to AM."})
    if masterminds_pending > 0:
        flags.append({"flag": "Mastermind Backlog", "severity": WARNING,
                      "detail": f"{masterminds_pending} masterminds pending. Review with PA before EOS."})
    if site_inferred_avg > 0 and inferred_time_pct > site_inferred_avg:
        flags.append({"flag": "Inferred Time Outlier", "severity": WARNING,
                      "detail": f"Inferred time {inferred_time_pct:.1%} > site avg {site_inferred_avg:.1%}."})
    if site_cycle_avg > 0 and cycle_time > site_cycle_avg:
        flags.append({"flag": "Cycle Time Outlier", "severity": WARNING,
                      "detail": f"Cycle time {cycle_time:.1f}s > site avg {site_cycle_avg:.1f}s."})
    if site_loss_avg > 0 and process_loss_pct > site_loss_avg:
        flags.append({"flag": "Process Loss Outlier", "severity": WARNING,
                      "detail": f"Process loss {process_loss_pct:.1%} > site avg {site_loss_avg:.1%}."})
    return flags
