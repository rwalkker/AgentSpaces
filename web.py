#!/usr/bin/env python3
"""Remmy Shift Planner — Web Frontend."""

import sys, os, json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template_string, request, jsonify, session as flask_session
from remmy.db import init_db
from remmy.engine.roles import Quarter, QUARTERLY_WEIGHTS
from remmy.engine.hc import compute_full_plan
from remmy.engine.positioning import determine_positioning
from remmy.engine.dilution import get_dilution_factor
from remmy.engine.volume import compute_day_night_split, convergence_check, compute_whd_volume
from remmy.engine.rate import get_all_rolling_averages, get_ns_rolling_average
from remmy.conversation.intent import classify_intent, extract_number, extract_role_code, extract_shift_type
from remmy.conversation.qa import handle_question
from remmy.conversation.session import SessionState
from remmy.guardrails.flags import format_flag, blocks_finalization, check_show_rate
from remmy.guardrails.overrides import apply_override, get_override_history
from remmy.export.artifact import render_artifact
from remmy.export.formats import export_csv, export_slack
from remmy.learning.loop import generate_weekly_summary, check_baseline_stale

app = Flask(__name__)
app.secret_key = os.urandom(24)

# In-memory session states per user
sessions: dict[str, SessionState] = {}


def get_state(sid: str) -> SessionState:
    if sid not in sessions:
        sessions[sid] = SessionState()
        sessions[sid].quarter = get_current_quarter()
    return sessions[sid]


def get_current_quarter() -> int:
    m = datetime.now().month
    return 1 if m <= 3 else 2 if m <= 6 else 3 if m <= 9 else 4


def process_message(text: str, state: SessionState) -> list[str]:
    """Process user message and return list of response lines."""
    responses = []
    intent = classify_intent(text)

    if intent == "help":
        responses.append(HELP_TEXT)
    elif intent == "create_plan":
        shift = extract_shift_type(text)
        if shift:
            state.shift_type = shift
        missing = state.get_missing_inputs()
        if missing:
            attr, question = missing[0]
            responses.append(question)
            state._pending_attr = attr
        else:
            responses.extend(build_plan_web(state))
    elif intent == "ask_question":
        responses.append(handle_question(text, state))
    elif intent == "lock_plan":
        if not state.has_plan():
            responses.append("No plan to lock. Build one first.")
        elif blocks_finalization(state.plan_result.flags):
            responses.append("🔴 Critical flags must be resolved before locking.")
        else:
            state.status = "locked"
            state.locked_by = state.planning_om
            state.locked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            responses.append(f"🔒 Plan locked by {state.locked_by} at {state.locked_at}")
    elif intent == "show_plan":
        if state.has_plan():
            responses.append(f"<pre>{render_artifact(state.plan_result, state.plan_data)}</pre>")
        else:
            responses.append("No plan generated yet. Say 'build a day shift plan' to start.")
    elif intent == "export":
        if state.has_plan():
            if "csv" in text.lower():
                responses.append(f"<pre>{export_csv(state.plan_result, state.plan_data)}</pre>")
            elif "slack" in text.lower():
                responses.append(f"<pre>{export_slack(state.plan_result, state.plan_data)}</pre>")
            else:
                responses.append(f"<pre>{render_artifact(state.plan_result, state.plan_data)}</pre>")
        else:
            responses.append("No plan to export.")
    elif intent == "apply_override":
        responses.extend(handle_override_web(text, state))
    elif intent == "close_artifact":
        responses.append("✅ Artifact closed. Rolling averages updated.")
    else:
        # Check if we're collecting inputs
        if hasattr(state, '_pending_attr') and state._pending_attr:
            attr = state._pending_attr
            val = text.strip()
            if attr in ("big_gulp_volume", "shift_duration"):
                try:
                    val = float(val.replace(",", ""))
                except ValueError:
                    responses.append(f"Please enter a number for {attr}.")
                    return responses
            setattr(state, attr, val)
            state._pending_attr = None
            missing = state.get_missing_inputs()
            if missing:
                attr, question = missing[0]
                state._pending_attr = attr
                responses.append(question)
            else:
                # All inputs gathered — ask for remaining optional inputs or build
                responses.extend(collect_optional_inputs(state))
        else:
            responses.append(handle_question(text, state))

    return responses


def collect_optional_inputs(state: SessionState) -> list[str]:
    """After required inputs, set defaults and build."""
    if not state.show_rate_day:
        state.show_rate_day = 0.85
    if not state.show_rate_night:
        state.show_rate_night = 0.85
    if not state.seed_hc_day:
        state.seed_hc_day = 0
    if not state.seed_hc_night:
        state.seed_hc_night = 0
    if not state.prior_shift_hit:
        state.prior_shift_hit = "hit"
    state.new_hire_prompted = True
    return build_plan_web(state)


def build_plan_web(state: SessionState) -> list[str]:
    responses = []
    q = Quarter(state.quarter)

    day_pct, night_pct = compute_day_night_split(
        state.seed_hc_day or 1, state.seed_hc_night or 1,
        state.show_rate_day, state.show_rate_night,
        state.shift_duration,
    )
    shift_volume = state.big_gulp_volume * (day_pct if state.shift_type == "Day" else night_pct)

    pos = determine_positioning(state.backlog_current, state.backlog_target, state.prior_shift_hit)
    for f in pos.flags:
        responses.append(format_flag(f))

    dilution_factor, dil_flags = get_dilution_factor(state.new_hire_pct)
    for f in dil_flags:
        responses.append(format_flag(f))

    cret_rolling, _ = get_all_rolling_averages("CRET")
    whd_rolling, _ = get_all_rolling_averages("WHD")

    ns_pct, _ = get_ns_rolling_average()
    state.ns_pct = ns_pct if ns_pct is not None else 0.15

    result = compute_full_plan(
        shift_volume=shift_volume, shift_duration=state.shift_duration,
        quarter=q, ns_pct=state.ns_pct, new_hire_pct=state.new_hire_pct,
        new_hire_count=state.new_hire_count, dilution_factor=dilution_factor,
        cret_rolling=cret_rolling or None, whd_rolling=whd_rolling or None,
        positioning_adj=pos.adjustment,
    )

    state.plan_result = result
    state.plan_data = {
        "site": "PHX6", "shift_type": state.shift_type, "date": state.date,
        "planning_om": state.planning_om, "big_gulp_volume": state.big_gulp_volume,
        "shift_volume_cret": shift_volume,
        "shift_volume_whd": compute_whd_volume(shift_volume),
        "shift_duration": state.shift_duration,
        "day_pct": day_pct * 100, "night_pct": night_pct * 100,
        "ns_pct": state.ns_pct * 100, "seed_hc": state.seed_hc_day,
        "positioning_label": pos.label, "positioning_adj": pos.adjustment,
        "backlog_current": state.backlog_current, "backlog_target": state.backlog_target,
        "prior_shift_hit": state.prior_shift_hit, "quarter": state.quarter,
        "status": state.status,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }

    artifact = render_artifact(result, state.plan_data)
    responses.append(f"<pre>{artifact}</pre>")

    if blocks_finalization(result.flags):
        responses.append("🔴 Critical flags present — resolve before finalizing.")

    return responses


def handle_override_web(text: str, state: SessionState) -> list[str]:
    if not state.has_plan():
        return ["No plan to override. Build one first."]
    role = extract_role_code(text)
    val = extract_number(text)
    if not role or val is None:
        return ["Specify role and value, e.g. 'override CRET-PICK to 15'"]
    original = (state.plan_result.cret_direct.get(role) or
                state.plan_result.cret_support.get(role) or
                state.plan_result.whd_direct.get(role) or 0)
    state.overrides[role] = int(val)
    return [f"✅ Override: {role} {original} → {int(val)}. Recalculating..."] + build_plan_web(state)


HELP_TEXT = """<b>Commands:</b>
• <b>build a day/night shift plan</b> — start a new plan
• <b>show plan</b> — display current artifact
• <b>override CRET-PICK to 15</b> — override a role
• <b>lock</b> — finalize the plan
• <b>export csv/slack</b> — export plan
• <b>why is my support % high?</b> — ask questions
• <b>help</b> — show this"""


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Remmy — Shift Planner</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f1117; color: #e0e0e0; height: 100vh; display: flex; flex-direction: column; }
  .header { background: #1a1d27; padding: 16px 24px; border-bottom: 1px solid #2a2d3a; display: flex; align-items: center; gap: 12px; }
  .header .logo { font-size: 24px; }
  .header h1 { font-size: 18px; font-weight: 600; color: #00d4aa; }
  .header .badge { background: #00d4aa22; color: #00d4aa; padding: 2px 10px; border-radius: 12px; font-size: 12px; }
  .chat { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
  .msg { max-width: 85%; padding: 12px 16px; border-radius: 12px; line-height: 1.5; font-size: 14px; }
  .msg.bot { background: #1e2130; align-self: flex-start; border: 1px solid #2a2d3a; }
  .msg.user { background: #00d4aa22; align-self: flex-end; border: 1px solid #00d4aa44; }
  .msg pre { background: #0a0c12; padding: 12px; border-radius: 8px; overflow-x: auto; font-size: 12px; margin: 8px 0; white-space: pre-wrap; word-wrap: break-word; font-family: 'Cascadia Code', 'Fira Code', monospace; }
  .msg b { color: #00d4aa; }
  .input-area { padding: 16px 24px; background: #1a1d27; border-top: 1px solid #2a2d3a; display: flex; gap: 12px; }
  .input-area input { flex: 1; background: #0f1117; border: 1px solid #2a2d3a; color: #e0e0e0; padding: 12px 16px; border-radius: 8px; font-size: 14px; outline: none; }
  .input-area input:focus { border-color: #00d4aa; }
  .input-area button { background: #00d4aa; color: #0f1117; border: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 14px; }
  .input-area button:hover { background: #00eabb; }
  .typing { color: #888; font-style: italic; font-size: 13px; }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: #0f1117; }
  ::-webkit-scrollbar-thumb { background: #2a2d3a; border-radius: 3px; }
</style>
</head>
<body>
<div class="header">
  <span class="logo">🤖</span>
  <h1>Remmy Shift Planner</h1>
  <span class="badge">PHX6 | Q{{ quarter }} Active</span>
</div>
<div class="chat" id="chat">
  <div class="msg bot">Welcome to Remmy! I'm your AI shift planning partner for PHX6.<br><br>
  ℹ️ Q{{ quarter }} Active — rate adjustment {{ q_adj }}%<br><br>
  Type <b>build a day shift plan</b> to get started, or <b>help</b> for all commands.</div>
</div>
<div class="input-area">
  <input type="text" id="input" placeholder="Type a message..." autocomplete="off" />
  <button onclick="send()">Send</button>
</div>
<script>
const chat = document.getElementById('chat');
const input = document.getElementById('input');
input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });

function addMsg(text, cls) {
  const d = document.createElement('div');
  d.className = 'msg ' + cls;
  d.innerHTML = text;
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
}

async function send() {
  const text = input.value.trim();
  if (!text) return;
  addMsg(text, 'user');
  input.value = '';
  addMsg('<span class="typing">Remmy is thinking...</span>', 'bot');

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text})
    });
    const data = await res.json();
    chat.removeChild(chat.lastChild); // remove typing
    data.responses.forEach(r => addMsg(r, 'bot'));
  } catch(e) {
    chat.removeChild(chat.lastChild);
    addMsg('⚠️ Error: ' + e.message, 'bot');
  }
}
</script>
</body>
</html>"""


@app.route("/")
def index():
    q = get_current_quarter()
    adj = f"{QUARTERLY_WEIGHTS[Quarter(q)] - 25:+.1f}"
    return render_template_string(HTML_TEMPLATE, quarter=q, q_adj=adj)


@app.route("/api/chat", methods=["POST"])
def chat_api():
    data = request.get_json()
    msg = data.get("message", "")
    sid = request.remote_addr or "default"
    state = get_state(sid)
    responses = process_message(msg, state)
    return jsonify({"responses": responses})


if __name__ == "__main__":
    print("Initializing database...")
    try:
        init_db()
    except Exception as e:
        print(f"DB warning: {e}")
    print("\n🤖 Remmy Web UI starting on http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
