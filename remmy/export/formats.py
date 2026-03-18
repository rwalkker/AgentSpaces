"""Export module — PDF, CSV, Slack-formatted output."""

import csv
import io
from remmy.engine.hc import HCResult
from remmy.engine.roles import CRET_DIRECT, CRET_SUPPORT, WHD_DIRECT
from remmy.export.artifact import render_artifact


def export_csv(result: HCResult, plan_data: dict) -> str:
    """Export HC plan as CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Model", "Role Code", "Role Name", "Type", "HC", "UPH", "Volume"])
    for role in CRET_DIRECT:
        writer.writerow(["CRET", role.code, role.name, "Direct",
                         result.cret_direct.get(role.code, 0),
                         result.cret_uph_map.get(role.code, 0),
                         result.cret_role_volumes.get(role.code, 0)])
    for role in CRET_SUPPORT:
        writer.writerow(["CRET", role.code, role.name, "Support",
                         result.cret_support.get(role.code, 0), "", ""])
    for role in WHD_DIRECT:
        writer.writerow(["AR/WHD", role.code, role.name, "Direct",
                         result.whd_direct.get(role.code, 0),
                         result.whd_uph_map.get(role.code, 0),
                         result.whd_role_volumes.get(role.code, 0)])
    writer.writerow(["AR/WHD", "INDIRECT", "Indirect Buffer", "Indirect",
                     result.whd_indirect_buffer, "", ""])
    writer.writerow([])
    writer.writerow(["", "", "BUILDING TOTAL", "", result.building_total, "", ""])
    return output.getvalue()


def export_slack(result: HCResult, plan_data: dict) -> str:
    """Export as Slack-formatted markdown."""
    lines = [
        f"*SHIFT PLAN | {plan_data.get('site', 'PHX6')} | {plan_data.get('shift_type', '')} | {plan_data.get('date', '')}*",
        f"Planning OM: {plan_data.get('planning_om', '')}",
        "",
        f"*Volume:* {plan_data.get('big_gulp_volume', 0):,.0f} units | *Duration:* {plan_data.get('shift_duration', 0)}h",
        f"*Positioning:* {plan_data.get('positioning_label', 'On Course')} ({plan_data.get('positioning_adj', 0):+.0f}%)",
        "",
        f"*CRET:* {result.total_cret_hc} HC (Direct: {result.total_direct_hc} | Support: {result.total_support_hc} @ {result.support_pct:.1%})",
        f"*AR/WHD:* {result.total_whd_hc} HC (Direct: {result.total_whd_direct} | Buffer: {result.whd_indirect_buffer})",
        f"*Building Total: {result.building_total} HC*",
    ]
    if result.flags:
        lines.append("")
        lines.append("*Flags:*")
        for f in result.flags:
            sym = {"critical": "🔴", "warning": "🟡", "info": "ℹ️"}.get(f["severity"], "")
            lines.append(f"  {sym} {f['flag']}: {f['detail']}")
    return "\n".join(lines)


def export_pdf(result: HCResult, plan_data: dict, filepath: str):
    """Export as PDF using reportlab."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError:
        # Write plain text fallback
        with open(filepath, "w") as f:
            f.write(render_artifact(result, plan_data))
        return

    c = canvas.Canvas(filepath, pagesize=letter)
    width, height = letter
    text = render_artifact(result, plan_data)
    y = height - 40
    for line in text.split("\n"):
        if y < 40:
            c.showPage()
            y = height - 40
        c.setFont("Courier", 8)
        c.drawString(40, y, line[:120])
        y -= 12
    c.save()


def save_csv(result: HCResult, plan_data: dict, filepath: str):
    with open(filepath, "w") as f:
        f.write(export_csv(result, plan_data))


def save_slack(result: HCResult, plan_data: dict, filepath: str):
    with open(filepath, "w") as f:
        f.write(export_slack(result, plan_data))
