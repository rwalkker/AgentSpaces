"""Shift plan artifact renderer — exact format from spec."""

from remmy.engine.hc import HCResult
from remmy.engine.roles import CRET_DIRECT, CRET_SUPPORT, WHD_DIRECT, Quarter, QUARTERLY_WEIGHTS
from remmy.guardrails.flags import format_flag, SEVERITY_SYMBOLS

SEPARATOR = "═" * 55


def render_artifact(result: HCResult, plan_data: dict,
                    override_history: list[dict] | None = None,
                    eos_quality: list[dict] | None = None) -> str:
    q = plan_data.get("quarter", 1)
    qe = Quarter(q)
    lines = [
        SEPARATOR,
        f"SHIFT PLAN ARTIFACT | {plan_data.get('site', 'PHX6')} | {plan_data.get('shift_type', 'Day')} | {plan_data.get('date', '')}",
        f"Planning OM: {plan_data.get('planning_om', '')} | Generated: {plan_data.get('timestamp', '')} | v1.1",
        SEPARATOR,
        "",
        "VOLUME INPUTS",
        f"  Big Gulp Volume:       {plan_data.get('big_gulp_volume', 0):,.0f} units",
        f"  Day/Night Split:       {plan_data.get('day_pct', 50):.1f}% / {plan_data.get('night_pct', 50):.1f}%",
        f"  Shift Volume (CRET):   {plan_data.get('shift_volume_cret', 0):,.0f} units",
        f"  Shift Volume (AR/WHD): {plan_data.get('shift_volume_whd', 0):,.0f} (CRET Vol × 3%) (Auto-Calculated)",
        f"  Shift Duration:        {plan_data.get('shift_duration', 0)} hours",
        "",
        "ASSUMED INPUTS (Auto-Calculated — Review Before Finalizing)",
        f"  NS% Applied:      {plan_data.get('ns_pct', 0):.1f}%",
        f"  AR/WHD Volume:    {plan_data.get('shift_volume_whd', 0):,.0f} (CRET Vol × 3%)",
        f"  Seed HC Used:     {plan_data.get('seed_hc', 'N/A')}",
        f"  Day/Night Split:  Calculated from show hours ratio",
        "  Any value can be overridden before finalizing.",
        "",
        "POSITIONING STRATEGY",
        f"  Strategy: {plan_data.get('positioning_label', '✅ On Course')}",
        f"  Adjustment: {plan_data.get('positioning_adj', 0):+.0f}%",
        f"  Backlog: {plan_data.get('backlog_current', 'N/A')} vs {plan_data.get('backlog_target', 'N/A')}",
        f"  Prior Shift: {plan_data.get('prior_shift_hit', 'N/A')}",
        "",
        "QUARTERLY CONTEXT",
        f"  Quarter: Q{q} | Weight: {QUARTERLY_WEIGHTS[qe]}% | Rate Adj: {(QUARTERLY_WEIGHTS[qe] - 25):+.1f}%",
        "",
    ]

    # CRET HC Plan
    lines.append("CRET HEADCOUNT PLAN")
    lines.append("  Direct Labor:")
    for role in CRET_DIRECT:
        hc = result.cret_direct.get(role.code, 0)
        uph = result.cret_uph_map.get(role.code, 0)
        vol = result.cret_role_volumes.get(role.code, 0)
        lines.append(f"    {role.code:<16} {role.name:<14} HC: {hc:>3}  |  UPH: {uph:>6.1f}  |  Vol: {vol:>8,.0f}")
    lines.append(f"  Total Direct HC: {result.total_direct_hc}")
    lines.append("")
    lines.append("  Support Labor:")
    for role in CRET_SUPPORT:
        hc = result.cret_support.get(role.code, 0)
        label = role.name
        if role.code == "CRET-LEAD" and result.ambassador_hc > 0:
            label = "Ambassador"
        lines.append(f"    {role.code:<16} {label:<14} HC: {hc:>3}")
    lines.append(f"  Total Support HC: {result.total_support_hc} | Support %: {result.support_pct:.1%} (Target: 6.47% | Ceiling: 19.2%)")
    lines.append(f"  TOTAL CRET HC: {result.total_cret_hc}")
    lines.append("")

    # AR/WHD HC Plan
    lines.append("AR/WHD HEADCOUNT PLAN")
    for role in WHD_DIRECT:
        hc = result.whd_direct.get(role.code, 0)
        uph = result.whd_uph_map.get(role.code, 0)
        vol = result.whd_role_volumes.get(role.code, 0)
        lines.append(f"    {role.code:<16} {role.name:<14} HC: {hc:>3}  |  UPH: {uph:>6.1f}  |  Vol: {vol:>8,.0f}")
    lines.append(f"  Total Direct HC: {result.total_whd_direct} | Indirect Buffer: {result.whd_indirect_buffer} HC (8% floor rounded)")
    lines.append(f"  TOTAL AR/WHD HC: {result.total_whd_hc}")
    lines.append("")
    lines.append(f"  BUILDING TOTAL: CRET {result.total_cret_hc} + AR/WHD {result.total_whd_hc} = {result.building_total} HC")
    lines.append("")

    # Escalation Flags
    lines.append("ESCALATION FLAGS")
    if result.flags:
        for f in result.flags:
            lines.append(f"  {format_flag(f)}")
    else:
        lines.append("  ✅ No flags — plan within all guardrails")
    lines.append("")

    # EOS Quality Targets (v1.3)
    if eos_quality:
        lines.append("EOS QUALITY TARGETS")
        for f in eos_quality:
            lines.append(f"  {format_flag(f)}")
        lines.append("")

    # Override History
    lines.append("OVERRIDE HISTORY")
    if override_history:
        for o in override_history:
            lines.append(
                f"  {o['timestamp']} | {o['role_code']} | Original: {o['original']} | "
                f"Override: {o['override']} | Justification: {o['justification']} | Type: {o['type']}"
            )
    else:
        lines.append("  No overrides — plan reflects all calculated values.")
    lines.append("")

    status = plan_data.get("status", "draft")
    if status == "locked":
        lines.append(f"STATUS: 🔒 Locked by {plan_data.get('locked_by', '')} at {plan_data.get('locked_at', '')}")
    else:
        lines.append("STATUS: 🔓 Draft")
    lines.append(SEPARATOR)

    return "\n".join(lines)
