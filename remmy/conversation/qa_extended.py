"""Q&A handler — continued (Q4, Q5, errors)."""

from remmy.conversation.session import SessionState


def _q4_hc_vs_rate(state: SessionState) -> str:
    return (
        "Whether to increase HC or adjust rate depends on your situation:\n\n"
        "  Increase HC when:\n"
        "    - Headcount is available\n"
        "    - Rates are at or above baseline\n"
        "    - You need more throughput capacity\n\n"
        "  Adjust rate when:\n"
        "    - Headcount-constrained (no more people available)\n"
        "    - Crew is tenured and can sustain higher rates\n"
        "    - Current rates are below baseline (room to improve)\n\n"
        "I can pull your 4-week rate performance data to help decide.\n"
        "Want me to check the rolling averages?"
    )


def _q5_support_overload(state: SessionState) -> str:
    if not state.plan_result:
        return "I need a plan generated first to diagnose support overload."
    r = state.plan_result
    ps_hc = r.cret_support.get("CRET-PS", 0)
    formula_ps = max(r.total_direct_hc // 40, 0)
    lines = [
        f"Support % is {r.support_pct:.1%} — exceeds 19.2% FHN ceiling.",
        "",
        "Root cause analysis:",
        f"  PS HC: {ps_hc} (formula value would be {formula_ps})",
        f"  Total Support: {r.total_support_hc} | Total Direct: {r.total_direct_hc}",
        "",
        "Options to resolve:",
        f"  1. Reduce PS to formula value ({formula_ps}) — recommended baseline",
        "  2. Increase Direct HC to dilute the support %",
        "  3. Justify override with one-line note (logged in Override History)",
        "",
        "PS is always formula-driven (Direct HC ÷ 40) — no fixed minimum.",
    ]
    return "\n".join(lines)


def _error_1_1(state: SessionState) -> str:
    return (
        "🔴 Volume Mismatch detected: Day + Night volumes don't equal Big Gulp.\n\n"
        "I can propose a proportional correction to realign the split.\n"
        "Want me to recalculate, or do you want to manually adjust?"
    )


def _error_3_1(state: SessionState) -> str:
    if not state.is_locked():
        return "This plan isn't locked. You can modify it directly."
    return (
        "This plan is 🔒 Locked. You have 4 options:\n\n"
        "  1. Unlock — resets hourly tracking, allows full edits\n"
        "  2. New plan — create a fresh plan for the next shift\n"
        "  3. Notes only — add notes without changing the plan\n"
        "  4. Mid-Shift Amendment — timestamped amendment attached to locked plan;\n"
        "     hourly tracking continues against original baseline;\n"
        "     flagged for post-shift debrief\n\n"
        "Which option?"
    )


def _generic_answer(text: str, state: SessionState) -> str:
    return (
        "I'm not sure I understand that question in the current context.\n"
        "I can help with:\n"
        "  - Building shift plans (\"build a day shift plan\")\n"
        "  - Explaining calculations (\"why is my support % high?\")\n"
        "  - Overrides (\"override CRET-PICK to 15\")\n"
        "  - Exporting (\"export to PDF\")\n"
        "  - Locking/closing plans\n\n"
        "Type 'help' for a full list of commands."
    )
