"""Q&A handler — advisory responses (Q1-Q5) and error detection (1.1-3.1)."""

import re
from remmy.conversation.session import SessionState
from remmy.conversation.qa_extended import _q4_hc_vs_rate, _q5_support_overload, _error_1_1, _error_3_1, _generic_answer
from remmy.engine.roles import CRET_SUPPORT


def handle_question(text: str, state: SessionState) -> str:
    t = text.lower()
    if any(w in t for w in ["indirect", "support", "budget", "high"]):
        return _q1_indirect_budget(state)
    if "lp rate" in t or "support rate" in t:
        return _q2_rate_definitions(state)
    if any(w in t for w in ["only", "showed", "show", "attendance", "40 people", "short"]):
        return _q3_staffing_shortfall(text, state)
    if any(w in t for w in ["increase hc", "adjust rate", "which lever", "add head"]):
        return _q4_hc_vs_rate(state)
    if "overload" in t or ("support" in t and ("clear" in t or "won't" in t or "flag" in t)):
        return _q5_support_overload(state)
    if "volume mismatch" in t or "doesn't add up" in t:
        return _error_1_1(state)
    if "locked" in t and ("modify" in t or "change" in t or "edit" in t):
        return _error_3_1(state)
    return _generic_answer(text, state)


def _q1_indirect_budget(state: SessionState) -> str:
    if not state.plan_result:
        return "I need a plan generated first to explain the indirect budget. Want to build one?"
    r = state.plan_result
    ps_hc = r.cret_support.get("CRET-PS", 0)
    lines = [
        "Here's the breakdown of your indirect/support budget:",
        "",
        f"  Total Direct HC: {r.total_direct_hc}",
        f"  Support Budget = Direct HC × 6.47% (ceiling) = {r.total_support_hc}",
        f"  PS HC = Direct HC ÷ 40 = {ps_hc} (calculated first — priority anchor)",
        f"  Remaining Budget = {r.total_support_hc - ps_hc} → split across {len(CRET_SUPPORT) - 1} roles",
        f"  Support %: {r.support_pct:.1%} (Target: 6.47% | Ceiling: 19.2%)",
        "",
        "If it looks high, your options are:",
        "  1. Reduce PS to formula value (Direct HC ÷ 40) if it was overridden",
        "  2. Increase Direct HC to dilute the support %",
        "  3. Reduce one non-PS support role by 1 HC",
        "",
        "⚠️ Review the Assumed Inputs block before finalizing.",
    ]
    return "\n".join(lines)


def _q2_rate_definitions(state: SessionState) -> str:
    return (
        "LP Rate vs LP Support Rate:\n\n"
        "  LP Rate = direct processing speed (UPH by direct labor only)\n"
        "  LP Support Rate = total operation efficiency (UPH including indirect labor)\n\n"
        "LP Support Rate is always lower because it divides the same volume\n"
        "by more labor hours (direct + indirect)."
    )


def _q3_staffing_shortfall(text: str, state: SessionState) -> str:
    # Try to extract actual attendance number
    m = re.search(r"(\d+)\s*(?:people|showed|hc|heads)", text.lower())
    actual = int(m.group(1)) if m else None
    planned = state.plan_result.building_total if state.plan_result else 0

    lines = ["Your plan shows more HC than actually showed up. Here are your options:", ""]
    if actual and planned:
        gap = planned - actual
        gap_pct = gap / planned * 100 if planned > 0 else 0
        lines.insert(0, f"Planned: {planned} HC | Actual: {actual} HC | Gap: {gap} ({gap_pct:.0f}%)\n")

    lines.extend([
        "  1. Reduce volume proportionally — safest option, triggers convergence check",
        "  2. Increase UPH targets — risky, only if crew is tenured",
        "  3. Apply Underprocess positioning — accept lower throughput",
        "  4. Shift volume to next shift — if backlog allows",
        "",
        "Which option works for your situation?",
    ])
    return "\n".join(lines)
