"""Text / markdown / JSON / CSV output."""
from __future__ import annotations

import csv
import io
import json

from .core import Report


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _note(r: Report) -> str:
    if r.private is False:
        return ("Public repo: standard GitHub-hosted runners are free here. Figures show what these "
                "minutes would cost at list price on a private repo.")
    return "List-price estimate. Jobs rounded up to whole minutes; size multiplier from runner labels."


def text(r: Report, top: int = 10) -> str:
    t = r.total
    share = (t.rerun_cost / t.cost * 100) if t.cost else 0.0
    out = [f"runbill · {r.repo} · runs since {r.since} ({r.run_count} runs, {t.jobs} jobs)", ""]
    out.append(f"  TOTAL      {t.billed_minutes:>9,.0f} billed min   {_money(t.cost):>10}   "
               f"(raw {t.seconds / 60:,.0f} min, re-runs {share:.1f}%)")
    out.append("")
    out.append("  BY WORKFLOW" + " " * 30 + "runs    billed min        cost   share")
    for w in r.workflows[:top]:
        pct = (w.cost / t.cost * 100) if t.cost else 0.0
        out.append(f"  {w.key[:40]:<41} {w.runs:>4}  {w.billed_minutes:>12,.0f}  {_money(w.cost):>10}  {pct:>5.1f}%")
    out.append("")
    out.append(f"  TOP {min(top, len(r.jobs))} JOBS" + " " * 31 + "jobs    billed min        cost")
    for j in r.jobs[:top]:
        out.append(f"  {j.key[:40]:<41} {j.jobs:>4}  {j.billed_minutes:>12,.0f}  {_money(j.cost):>10}")
    out.append("")
    if r.truncated:
        out.append("  ! stopped at --max-runs; totals cover only the newest runs.")
    out.append("  " + _note(r))
    return "\n".join(out)


def markdown(r: Report, top: int = 10) -> str:
    t = r.total
    share = (t.rerun_cost / t.cost * 100) if t.cost else 0.0
    lines = [f"### runbill · `{r.repo}` since {r.since}", "",
             f"**{t.billed_minutes:,.0f} billed minutes · {_money(t.cost)}** across {r.run_count} runs "
             f"/ {t.jobs} jobs · re-runs {share:.1f}% of cost", "",
             "| Workflow | Runs | Billed min | Cost | Share |", "|---|---:|---:|---:|---:|"]
    for w in r.workflows[:top]:
        pct = (w.cost / t.cost * 100) if t.cost else 0.0
        lines.append(f"| {w.key} | {w.runs} | {w.billed_minutes:,.0f} | {_money(w.cost)} | {pct:.1f}% |")
    lines += ["", "| Job | Jobs | Billed min | Cost |", "|---|---:|---:|---:|"]
    for j in r.jobs[:top]:
        lines.append(f"| {j.key} | {j.jobs} | {j.billed_minutes:,.0f} | {_money(j.cost)} |")
    lines += ["", f"_{_note(r)}_"]
    if r.truncated:
        lines.append("_Stopped at --max-runs; totals cover only the newest runs._")
    return "\n".join(lines) + "\n"


def as_json(r: Report) -> str:
    return json.dumps(r.as_dict(), indent=2, ensure_ascii=False)


def as_csv(r: Report) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["level", "name", "runs", "jobs", "raw_minutes", "billed_minutes", "cost_usd", "rerun_cost_usd"])
    for lvl, items in (("workflow", r.workflows), ("job", r.jobs)):
        for x in items:
            d = x.as_dict()
            w.writerow([lvl, d["name"], d["runs"], d["jobs"], d["raw_minutes"], d["billed_minutes"],
                        d["cost_usd"], d["rerun_cost_usd"]])
    return buf.getvalue()
