#!/usr/bin/env python3
"""Remmy Shift Planner Agent — Interactive CLI entry point."""

import sys
import os
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from remmy.db import init_db, get_session
from remmy.models import ShiftPlan
from remmy.engine.roles import Quarter, QUARTERLY_WEIGHTS
from remmy.engine.hc import compute_full_plan
from remmy.engine.positioning import determine_positioning
from remmy.engine.dilution import get_dilution_factor, compute_ambassador_hc
from remmy.engine.volume import compute_day_night_split, convergence_check, compute_whd_volume
from remmy.engine.rate import get_all_rolling_averages, get_ns_rolling_average
from remmy.conversation.intent import classify_intent, extract_number, extract_role_code, extract_shift_type
from remmy.conversation.session import SessionState
from remmy.conversation.qa import handle_question
from remmy.guardrails.flags import (
    format_flag, blocks_finalization, get_unacknowledged_warnings,
    check_show_rate, check_rate_outlier, SEVERITY_SYMBOLS,
)
from remmy.guardrails.overrides import apply_override, get_override_history, check_cascade_conflict
from remmy.guardrails.addenda import cross_check_indirect_ratios, check_ps_escalation_rate
from remmy.export.artifact import render_artifact
from remmy.export.formats import export_pdf, save_csv, save_slack
from remmy.learning.loop import (
    update_baseline_on_close, compute_planning_accuracy, record_learning_metric,
    check_baseline_stale, generate_weekly_summary, check_phase_regression,
)

# Colors
try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init()
except ImportError:
    class Fore:
        RED = YELLOW = GREEN = CYAN = MAGENTA = RESET = ""
    class Style:
        BRIGHT = RESET_ALL = ""


def color(text, fg):
    return f"{fg}{text}{Fore.RESET}"


def print_flag(f):
    sym = SEVERITY_SYMBOLS.get(f["severity"], "")
    fg = {
        "critical": Fore.RED, "warning": Fore.YELLOW, "info": Fore.CYAN,
    }.get(f["severity"], "")
    print(color(f"  {sym} {f['flag']} — {f['detail']}", fg))


def get_current_quarter() -> int:
    month = datetime.now().month
    if month <= 3: return 1
    if month <= 6: return 2
    if month <= 9: return 3
    return 4


def prompt(msg: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{color('Remmy', Fore.CYAN)}: {msg}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return val if val else default


def prompt_float(msg: str, default: float = 0) -> float:
    val = prompt(msg, str(default) if default else "")
    try:
        return float(val.replace(",", ""))
    except (ValueError, AttributeError):
        return default


def prompt_int(msg: str, default: int = 0) -> int:
    val = prompt(msg, str(default) if default else "")
    try:
        return int(float(val.replace(",", "")))
    except (ValueError, AttributeError):
        return default


def say(msg: str):
    print(f"{color('Remmy', Fore.CYAN)}: {msg}")


def gather_inputs(state: SessionState):
    """Gather all required inputs from OM conversationally."""
    missing = state.get_missing_inputs()
    for attr, question in missing:
        val = prompt(question)
        if attr in ("big_gulp_volume", "shift_duration"):
            try:
                val = float(val.replace(",", ""))
            except (ValueError, AttributeError):
                val = 0
        setattr(state, attr, val)

    # Quarter auto-detect
    state.quarter = get_current_quarter()
    say(f"ℹ️ Q{state.quarter} Active — rate adjustment {QUARTERLY_WEIGHTS[Quarter(state.quarter)] - 25:+.1f}%")

    # Show rates
    if not state.show_rate_day:
        state.show_rate_day = prompt_float("Day show rate (e.g. 0.85 for 85%)", 0.85)
    if not state.show_rate_night:
        state.show_rate_night = prompt_float("Night show rate", 0.85)

    # Show rate validation
    for label, rate in [("Day", state.show_rate_day), ("Night", state.show_rate_night)]:
        flags = check_show_rate(rate)
        for f in flags:
            print_flag(f)
            if f["severity"] == "critical":
                new_rate = prompt_float(f"Please re-enter {label} show rate")
                if label == "Day":
                    state.show_rate_day = new_rate
                else:
                    state.show_rate_night = new_rate

    # Seed HC
    if not state.seed_hc_day:
        state.seed_hc_day = prompt_float("Seed HC for Day (from ALPS or prior shift)", 0)
    if not state.seed_hc_night:
        state.seed_hc_night = prompt_float("Seed HC for Night", 0)

    # Backlog and prior shift
    if not state.backlog_current:
        state.backlog_current = prompt_float("Current backlog")
    if not state.backlog_target:
        state.backlog_target = prompt_float("Backlog target")
    if not state.prior_shift_hit:
        state.prior_shift_hit = prompt("Prior shift result (hit/miss/exceed)", "hit")

    # New hire prompt (proactive)
    if not state.new_hire_prompted:
        nh = prompt("Any new hires on this shift? Enter % (0 if none)", "0")
        try:
            state.new_hire_pct = float(nh.replace("%", "")) / 100 if float(nh.replace("%", "")) > 1 else float(nh)
        except ValueError:
            state.new_hire_pct = 0
        if state.new_hire_pct > 0:
            state.new_hire_count = prompt_int("How many new hires?")
        state.new_hire_prompted = True


def build_plan(state: SessionState):
    """Build the full shift plan from gathered inputs."""
    q = Quarter(state.quarter)

    # Day/Night split
    day_pct, night_pct = compute_day_night_split(
        state.seed_hc_day, state.seed_hc_night,
        state.show_rate_day, state.show_rate_night,
        state.shift_duration,
    )
    shift_volume = state.big_gulp_volume * (day_pct if state.shift_type == "Day" else night_pct)

    # Positioning
    pos = determine_positioning(
        state.backlog_current, state.backlog_target, state.prior_shift_hit,
    )
    state.flags.extend(pos.flags)
    for f in pos.flags:
        print_flag(f)

    # Dilution
    dilution_factor, dil_flags = get_dilution_factor(state.new_hire_pct)
    state.flags.extend(dil_flags)
    for f in dil_flags:
        print_flag(f)

    # Rolling averages (from DB if available)
    cret_rolling, cret_flags = get_all_rolling_averages("CRET")
    whd_rolling, whd_flags = get_all_rolling_averages("WHD")
    state.flags.extend(cret_flags + whd_flags)

    # NS%
    ns_pct, ns_flags = get_ns_rolling_average()
    if ns_pct is not None:
        state.ns_pct = ns_pct
        state.flags.extend(ns_flags)
        say(f"ℹ️ NS% Applied: {ns_pct:.1%} from 4-week rolling average")
    else:
        state.ns_pct = prompt_float("NS% not available from history. Enter NS% (e.g. 0.15 for 15%)", 0.15)

    # Compute
    result = compute_full_plan(
        shift_volume=shift_volume,
        shift_duration=state.shift_duration,
        quarter=q,
        ns_pct=state.ns_pct,
        new_hire_pct=state.new_hire_pct,
        new_hire_count=state.new_hire_count,
        dilution_factor=dilution_factor,
        cret_rolling=cret_rolling or None,
        whd_rolling=whd_rolling or None,
        overrides=state.overrides,
        locks=state.locks,
        positioning_adj=pos.adjustment,
    )

    # Convergence check
    seed = state.seed_hc_day if state.shift_type == "Day" else state.seed_hc_night
    if seed and convergence_check(seed, result.building_total):
        say(f"⚠️ Final HC ({result.building_total}) deviates >10% from seed ({seed:.0f}). Recalculate split?")
        if prompt("Recalculate? (y/n)", "n").lower() == "y":
            # Recalculate with final HC as new seed
            if state.shift_type == "Day":
                state.seed_hc_day = result.total_cret_hc
            else:
                state.seed_hc_night = result.total_cret_hc
            return build_plan(state)  # recursive recalc

    # Stale baseline check
    state.flags.extend(check_baseline_stale())

    # Merge flags
    result.flags.extend(state.flags)

    state.plan_result = result
    state.plan_data = {
        "site": "PHX6",
        "shift_type": state.shift_type,
        "date": state.date,
        "planning_om": state.planning_om,
        "big_gulp_volume": state.big_gulp_volume,
        "shift_volume_cret": shift_volume,
        "shift_volume_whd": compute_whd_volume(shift_volume),
        "shift_duration": state.shift_duration,
        "day_pct": day_pct * 100,
        "night_pct": night_pct * 100,
        "ns_pct": state.ns_pct * 100,
        "seed_hc": seed,
        "positioning_label": pos.label,
        "positioning_adj": pos.adjustment,
        "backlog_current": state.backlog_current,
        "backlog_target": state.backlog_target,
        "prior_shift_hit": state.prior_shift_hit,
        "quarter": state.quarter,
        "status": state.status,
        "locked_by": state.locked_by,
        "locked_at": state.locked_at,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    # Save to DB
    save_plan_to_db(state)

    # Print artifact
    artifact = render_artifact(result, state.plan_data)
    print(artifact)

    # Flag summary
    if blocks_finalization(result.flags):
        say(color("🔴 Critical flags present — plan cannot be finalized until resolved.", Fore.RED))
    warnings = get_unacknowledged_warnings(result.flags, state.acknowledged_warnings)
    if warnings:
        say("🟡 Warnings require acknowledgment before finalizing:")
        for w in warnings:
            print_flag(w)
        if prompt("Acknowledge all warnings? (y/n)", "y").lower() == "y":
            for w in warnings:
                state.acknowledged_warnings.add(w["flag"])


def save_plan_to_db(state: SessionState):
    """Persist plan to PostgreSQL."""
    session = get_session()
    try:
        plan = ShiftPlan(
            site="PHX6",
            shift_type=state.shift_type,
            date=state.date,
            planning_om=state.planning_om,
            big_gulp_volume=state.big_gulp_volume,
            shift_volume_cret=state.plan_data.get("shift_volume_cret"),
            shift_volume_whd=state.plan_data.get("shift_volume_whd"),
            shift_duration=state.shift_duration,
            show_rate_day=state.show_rate_day,
            show_rate_night=state.show_rate_night,
            seed_hc_day=state.seed_hc_day,
            seed_hc_night=state.seed_hc_night,
            ns_pct=state.ns_pct,
            new_hire_pct=state.new_hire_pct,
            new_hire_count=state.new_hire_count,
            positioning=state.plan_result.flags[0]["flag"] if state.plan_result.flags else "on_course",
            positioning_adj=state.plan_data.get("positioning_adj", 0),
            backlog_current=state.backlog_current,
            backlog_target=state.backlog_target,
            prior_shift_hit=state.prior_shift_hit,
            quarter=state.quarter,
            status=state.status,
            cret_direct_hc=state.plan_result.cret_direct,
            cret_support_hc=state.plan_result.cret_support,
            whd_direct_hc=state.plan_result.whd_direct,
            whd_indirect_buffer=state.plan_result.whd_indirect_buffer,
            total_cret_hc=state.plan_result.total_cret_hc,
            total_whd_hc=state.plan_result.total_whd_hc,
            building_total=state.plan_result.building_total,
            support_pct=state.plan_result.support_pct,
            flags=[f for f in state.plan_result.flags],
        )
        session.add(plan)
        session.commit()
        state.plan_id = plan.id
    except Exception as e:
        say(f"⚠️ Could not save to database: {e}. Plan is still in memory.")
        session.rollback()
    finally:
        session.close()


def handle_override(text: str, state: SessionState):
    """Handle override commands."""
    if not state.has_plan():
        say("No plan to override. Build a plan first.")
        return
    if state.is_locked():
        say("Plan is locked. Unlock first, or use mid-shift amendment.")
        return

    role_code = extract_role_code(text)
    new_value = extract_number(text)
    if not role_code:
        role_code = prompt("Which role? (e.g. CRET-PICK)")
        role_code = extract_role_code(role_code) or role_code.upper()
    if new_value is None:
        new_value = prompt_float(f"New HC value for {role_code}")

    # Get original
    original = (state.plan_result.cret_direct.get(role_code) or
                state.plan_result.cret_support.get(role_code) or
                state.plan_result.whd_direct.get(role_code) or 0)

    is_lock = "lock" in text.lower()
    justification = ""
    if original > 0 and abs(new_value - original) / original > 0.20:
        justification = prompt(f"Override >{20}% — one-line justification required")
        if not justification:
            say("Hard override requires justification. Override cancelled.")
            return

    record, flags = apply_override(
        state.plan_id or 0, role_code, original, new_value,
        justification, force_lock=is_lock,
    )
    for f in flags:
        print_flag(f)
    if not record:
        return

    # Apply to state and recalculate
    state.overrides[role_code] = int(new_value)
    if is_lock:
        state.locks.add(role_code)
    say(f"✅ Override applied: {role_code} {original} → {int(new_value)} ({record.get('override_type', 'soft')})")

    # Rebuild plan with overrides
    say("Recalculating downstream...")
    state.flags = []
    build_plan(state)


def handle_lock(state: SessionState):
    if not state.has_plan():
        say("No plan to lock.")
        return
    if blocks_finalization(state.plan_result.flags):
        say(color("🔴 Cannot lock — critical flags must be resolved first.", Fore.RED))
        return
    warnings = get_unacknowledged_warnings(state.plan_result.flags, state.acknowledged_warnings)
    if warnings:
        say("🟡 Unacknowledged warnings — acknowledge before locking.")
        return
    state.status = "locked"
    state.locked_by = state.planning_om
    state.locked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    state.plan_data["status"] = "locked"
    state.plan_data["locked_by"] = state.locked_by
    state.plan_data["locked_at"] = state.locked_at
    # Update DB
    if state.plan_id:
        session = get_session()
        try:
            plan = session.query(ShiftPlan).get(state.plan_id)
            if plan:
                plan.status = "locked"
                plan.locked_by = state.locked_by
                plan.locked_at = datetime.now(timezone.utc)
                session.commit()
        finally:
            session.close()
    say(f"🔒 Plan locked by {state.locked_by} at {state.locked_at}")


def handle_close(state: SessionState):
    if not state.has_plan():
        say("No plan to close.")
        return
    say("Closing artifact and updating baselines...")
    if state.plan_id:
        # Prompt for actuals
        enter = prompt("Enter shift actuals for learning loop? (y/n)", "n")
        if enter.lower() == "y":
            handle_enter_actuals(state)
        update_baseline_on_close(state.plan_id)
        accuracy = compute_planning_accuracy(state.plan_id)
        if accuracy is not None:
            session = get_session()
            try:
                plan = session.query(ShiftPlan).get(state.plan_id)
                if plan:
                    record_learning_metric(plan, accuracy)
                    say(f"📊 Planning accuracy: {accuracy:.1%}")
            finally:
                session.close()
        phase, phase_flags = check_phase_regression()
        for f in phase_flags:
            print_flag(f)
    say("✅ Artifact closed. Rolling averages updated.")


def handle_enter_actuals(state: SessionState):
    """Prompt OM for actual HC/UPH per role."""
    from remmy.models import ShiftActual
    session = get_session()
    try:
        for code in list(state.plan_result.cret_direct.keys()) + list(state.plan_result.whd_direct.keys()):
            actual_hc = prompt_int(f"  {code} actual HC (enter to skip)", -1)
            if actual_hc < 0:
                continue
            actual_uph = prompt_float(f"  {code} actual UPH", 0)
            session.add(ShiftActual(
                plan_id=state.plan_id, role_code=code,
                actual_hc=actual_hc, actual_uph=actual_uph,
            ))
        session.commit()
    finally:
        session.close()


def handle_export(text: str, state: SessionState):
    if not state.has_plan():
        say("No plan to export.")
        return
    t = text.lower()
    overrides = get_override_history(state.plan_id or 0) if state.plan_id else []
    if "csv" in t:
        path = f"shift_plan_{state.date}_{state.shift_type}.csv"
        save_csv(state.plan_result, state.plan_data, path)
        say(f"📄 CSV exported to {path}")
    elif "slack" in t:
        path = f"shift_plan_{state.date}_{state.shift_type}_slack.txt"
        save_slack(state.plan_result, state.plan_data, path)
        say(f"📄 Slack format exported to {path}")
    elif "pdf" in t:
        path = f"shift_plan_{state.date}_{state.shift_type}.pdf"
        export_pdf(state.plan_result, state.plan_data, path)
        say(f"📄 PDF exported to {path}")
    else:
        # Default: print artifact
        artifact = render_artifact(state.plan_result, state.plan_data, overrides)
        print(artifact)


def show_help():
    print(f"""
{color('═══ REMMY SHIFT PLANNER — COMMANDS ═══', Fore.CYAN)}

  {color('Plan Creation:', Fore.GREEN)}
    "build a day shift plan"    Start a new plan
    "night shift plan"          Start a night plan

  {color('Modifications:', Fore.GREEN)}
    "override CRET-PICK to 15"  Override a role's HC
    "lock CRET-PS"              Lock a value through recalculation
    "what if I only have 40"    Explore scenarios

  {color('Questions:', Fore.GREEN)}
    "why is my support % high?" Explain calculations
    "LP rate vs support rate?"  Rate definitions
    "help"                      Show this help

  {color('Actions:', Fore.GREEN)}
    "show plan" / "artifact"    Display current plan
    "lock" / "finalize"         Lock the plan
    "close" / "eos"             Close artifact, update baselines
    "export pdf/csv/slack"      Export plan

  {color('Session:', Fore.GREEN)}
    "quit" / "exit"             End session
""")


def main():
    print(f"""
{color('═══════════════════════════════════════════════════', Fore.CYAN)}
{color('  REMMY SHIFT PLANNER AGENT v1.1 | PHX6', Fore.CYAN)}
{color('  Your AI-powered shift planning partner', Fore.CYAN)}
{color('═══════════════════════════════════════════════════', Fore.CYAN)}
""")

    # Init DB
    try:
        init_db()
    except Exception as e:
        say(f"⚠️ Database connection issue: {e}")
        say("Running in memory-only mode. Plans won't persist.")

    state = SessionState()
    state.quarter = get_current_quarter()
    q = Quarter(state.quarter)
    say(f"ℹ️ Q{state.quarter} Active — rate adjustment {QUARTERLY_WEIGHTS[q] - 25:+.1f}%")

    # Weekly summary if available
    try:
        summary = generate_weekly_summary()
        if "No shift data" not in summary:
            print(summary)
    except Exception:
        pass

    # Baseline stale check
    try:
        stale_flags = check_baseline_stale()
        for f in stale_flags:
            print_flag(f)
    except Exception:
        pass

    say("What would you like to do? (Type 'help' for commands)")
    print()

    while True:
        try:
            user_input = input(f"{color('OM', Fore.GREEN)}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            say("Goodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            say("Goodbye!")
            break

        state.conversation_history.append({"role": "om", "text": user_input})
        intent = classify_intent(user_input)

        if intent == "help":
            show_help()
        elif intent == "create_plan":
            shift = extract_shift_type(user_input)
            if shift:
                state.shift_type = shift
            gather_inputs(state)
            build_plan(state)
        elif intent == "modify_plan" or intent == "apply_override":
            handle_override(user_input, state)
        elif intent == "ask_question":
            response = handle_question(user_input, state)
            say(response)
        elif intent == "lock_plan":
            handle_lock(state)
        elif intent == "close_artifact":
            handle_close(state)
        elif intent == "export":
            handle_export(user_input, state)
        elif intent == "show_plan":
            if state.has_plan():
                overrides = get_override_history(state.plan_id or 0) if state.plan_id else []
                print(render_artifact(state.plan_result, state.plan_data, overrides))
            else:
                say("No plan generated yet. Want to build one?")
        elif intent == "enter_actuals":
            handle_enter_actuals(state)
        else:
            response = handle_question(user_input, state)
            say(response)

        print()


if __name__ == "__main__":
    main()
