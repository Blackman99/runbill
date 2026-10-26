"""Text / markdown / JSON / CSV output."""
from __future__ import annotations

import csv
import io
import json

from typing import List, Sequence, Tuple

from .compare import collapse_deltas
from .core import NO_BRANCH, UNKNOWN_EVENT, Line, OrgReport, Report, collapse

NAME_W = 40  # name column width in text tables
_TITLE = {"branch": "BY BRANCH", "event": "BY EVENT"}
_MD_HEAD = {"branch": "Branch", "event": "Event"}
_NOUN = {"branch": "branches", "event": "events"}
_PLACEHOLDERS = (NO_BRANCH, UNKNOWN_EVENT)


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _fit(s: str, middle: bool = False, w: int = NAME_W) -> str:
    """Shorten to w chars with an ellipsis. Branch names keep their tail (the distinctive part)."""
    if len(s) <= w:
        return s
    if middle:
        head = (w - 1) // 2
        return s[:head] + "…" + s[len(s) - (w - 1 - head):]
    return s[: w - 1] + "…"


def _pct(x: Line, t: Line) -> float:
    return (x.cost / t.cost * 100) if t.cost else 0.0


def _share_head(title: str) -> str:
    return f"  {title:<{NAME_W + 1}} {'runs':>4}  {'billed min':>12}  {'cost':>10}  {'share':>6}"


def _share_row(x: Line, t: Line, middle: bool = False) -> str:
    return (f"  {_fit(x.key, middle):<{NAME_W + 1}} {x.runs:>4}  {x.billed_minutes:>12,.0f}  "
            f"{_money(x.cost):>10}  {_pct(x, t):>5.1f}%")


def _text_groups(r, by: Sequence[str], top: int) -> List[str]:
    out: List[str] = []
    for g in by:
        rows, other = collapse(r.groups(g), top, _NOUN[g])
        out.append(_share_head(_TITLE[g]))
        out += [_share_row(x, r.total, middle=(g == "branch")) for x in rows]
        if other is not None:
            out.append(_share_row(other, r.total))
        if not rows:
            out.append("  (no runs)")
        if g == "branch" and any(_is_fork(x.key) for x in rows):
            out.append("  (owner:branch = pull request from a fork)")
        out.append("")
    return out


def _is_fork(key: str) -> bool:
    # Git ref names cannot contain ':', so a colon only comes from branch_key's fork marker.
    # In an org roll-up the key is "repo › branch"; look at the branch part only.
    return ":" in key.rsplit(" › ", 1)[-1]


def _md_name(key: str, g: str = "") -> str:
    """A table cell for a name. Branches and events are code spans; pipes are escaped for GFM tables."""
    cell = key.replace("|", "\\|")
    if g and key not in _PLACEHOLDERS and "`" not in key:
        return f"`{cell}`"
    return cell


def _md_groups(r, by: Sequence[str], top: int) -> List[str]:
    out: List[str] = []
    for g in by:
        rows, other = collapse(r.groups(g), top, _NOUN[g])
        out += ["", f"| {_MD_HEAD[g]} | Runs | Billed min | Cost | Share |", "|---|---:|---:|---:|---:|"]
        for x in rows:
            out.append(f"| {_md_name(x.key, g)} | {x.runs} | {x.billed_minutes:,.0f} | {_money(x.cost)} | "
                       f"{_pct(x, r.total):.1f}% |")
        if other is not None:
            out.append(f"| _{other.key}_ | {other.runs} | {other.billed_minutes:,.0f} | "
                       f"{_money(other.cost)} | {_pct(other, r.total):.1f}% |")
        if g == "branch" and any(_is_fork(x.key) for x in rows):
            out += ["", "<sub>`owner:branch` = pull request from a fork</sub>"]
    return out


def _note(r: Report) -> str:
    if r.private is False:
        return ("Public repo: standard GitHub-hosted runners are free here. Figures show what these "
                "minutes would cost at list price on a private repo.")
    return "List-price estimate. Jobs rounded up to whole minutes; runner type and size from labels."


def _org_note(r: OrgReport) -> str:
    if r.private is False:
        return ("All listed repos are public: standard GitHub-hosted runners are free there. "
                "Figures show what these minutes would cost at list price on a private repo.")
    if r.public_repos and r.private_repos:
        return (f"{r.public_repos} public / {r.private_repos} private repos with activity. "
                "Standard runners are free on public repos; figures are list-price estimates.")
    return "List-price estimate. Jobs rounded up to whole minutes; runner type and size from labels."


def text(r: Report, top: int = 10, by: Sequence[str] = ()) -> str:
    t = r.total
    share = (t.rerun_cost / t.cost * 100) if t.cost else 0.0
    out = [f"runbill · {r.repo} · runs since {r.since} ({r.run_count} runs, {t.jobs} jobs)", ""]
    out.append(f"  TOTAL      {t.billed_minutes:>9,.0f} billed min   {_money(t.cost):>10}   "
               f"(raw {t.seconds / 60:,.0f} min, re-runs {share:.1f}%)")
    out.append("")
    out.append(_share_head("BY WORKFLOW"))
    out += [_share_row(w, t) for w in r.workflows[:top]]
    out.append("")
    out += _text_groups(r, by, top)
    out.append(f"  {'TOP %d JOBS' % min(top, len(r.jobs)):<{NAME_W + 1}} {'jobs':>4}  {'billed min':>12}  "
               f"{'cost':>10}")
    for j in r.jobs[:top]:
        out.append(f"  {_fit(j.key):<{NAME_W + 1}} {j.jobs:>4}  {j.billed_minutes:>12,.0f}  {_money(j.cost):>10}")
    out.append("")
    if r.truncated:
        out.append("  ! stopped at --max-runs; totals cover only the newest runs.")
    out.append("  " + _note(r))
    return "\n".join(out)


def org_text(r: OrgReport, top: int = 10, by: Sequence[str] = ()) -> str:
    t = r.total
    share = (t.rerun_cost / t.cost * 100) if t.cost else 0.0
    out = [f"runbill · org {r.org} · runs since {r.since} "
           f"({r.repo_active}/{r.repo_scanned} repos, {r.run_count} runs, {t.jobs} jobs)", ""]
    out.append(f"  TOTAL      {t.billed_minutes:>9,.0f} billed min   {_money(t.cost):>10}   "
               f"(raw {t.seconds / 60:,.0f} min, re-runs {share:.1f}%)")
    out.append("")
    out.append(_share_head("BY REPO"))
    out += [_share_row(repo, t) for repo in r.repos[:top]]
    out.append("")
    out += _text_groups(r, by, top)
    if r.truncated:
        out.append("  ! stopped at --max-runs on one or more repos; totals cover only the newest runs.")
    out.append("  " + _org_note(r))
    return "\n".join(out)


def markdown(r: Report, top: int = 10, by: Sequence[str] = ()) -> str:
    t = r.total
    share = (t.rerun_cost / t.cost * 100) if t.cost else 0.0
    lines = [f"### runbill · `{r.repo}` since {r.since}", "",
             f"**{t.billed_minutes:,.0f} billed minutes · {_money(t.cost)}** across {r.run_count} runs "
             f"/ {t.jobs} jobs · re-runs {share:.1f}% of cost", "",
             "| Workflow | Runs | Billed min | Cost | Share |", "|---|---:|---:|---:|---:|"]
    for w in r.workflows[:top]:
        lines.append(f"| {_md_name(w.key)} | {w.runs} | {w.billed_minutes:,.0f} | {_money(w.cost)} | "
                     f"{_pct(w, t):.1f}% |")
    lines += _md_groups(r, by, top)
    lines += ["", "| Job | Jobs | Billed min | Cost |", "|---|---:|---:|---:|"]
    for j in r.jobs[:top]:
        lines.append(f"| {_md_name(j.key)} | {j.jobs} | {j.billed_minutes:,.0f} | {_money(j.cost)} |")
    lines += ["", f"_{_note(r)}_"]
    if r.truncated:
        lines.append("_Stopped at --max-runs; totals cover only the newest runs._")
    return "\n".join(lines) + "\n"


def org_markdown(r: OrgReport, top: int = 10, by: Sequence[str] = ()) -> str:
    t = r.total
    share = (t.rerun_cost / t.cost * 100) if t.cost else 0.0
    lines = [f"### runbill · org `{r.org}` since {r.since}", "",
             f"**{t.billed_minutes:,.0f} billed minutes · {_money(t.cost)}** across "
             f"{r.repo_active}/{r.repo_scanned} repos · {r.run_count} runs / {t.jobs} jobs · "
             f"re-runs {share:.1f}% of cost", "",
             "| Repo | Runs | Billed min | Cost | Share |", "|---|---:|---:|---:|---:|"]
    for repo in r.repos[:top]:
        lines.append(f"| {_md_name(repo.key)} | {repo.runs} | {repo.billed_minutes:,.0f} | "
                     f"{_money(repo.cost)} | {_pct(repo, t):.1f}% |")
    lines += _md_groups(r, by, top)
    lines += ["", f"_{_org_note(r)}_"]
    if r.truncated:
        lines.append("_Stopped at --max-runs on one or more repos; totals cover only the newest runs._")
    return "\n".join(lines) + "\n"


def as_json(r, by: Sequence[str] = ()) -> str:
    return json.dumps(r.as_dict(by), indent=2, ensure_ascii=False)


_CSV_HEAD = ["level", "name", "runs", "jobs", "raw_minutes", "billed_minutes", "cost_usd", "rerun_cost_usd"]


def _csv(sections) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_CSV_HEAD)
    for lvl, items in sections:
        for x in items:
            d = x.as_dict()
            w.writerow([lvl, d["name"], d["runs"], d["jobs"], d["raw_minutes"], d["billed_minutes"],
                        d["cost_usd"], d["rerun_cost_usd"]])
    return buf.getvalue()


def as_csv(r: Report, by: Sequence[str] = ()) -> str:
    """One row per workflow and job, plus every branch / event for --by (no 'other' folding in CSV)."""
    return _csv([("workflow", r.workflows), ("job", r.jobs)] + [(g, r.groups(g)) for g in by])


def org_csv(r: OrgReport, by: Sequence[str] = ()) -> str:
    return _csv([("repo", r.repos)] + [(g, r.groups(g)) for g in by])


# --- --compare -----------------------------------------------------------------------------------

CMP_W = 28  # minimum name column width in compare tables (it grows to NAME_W for long names)
_CMP_SECTIONS = {  # key: (text title, markdown head, plural noun, keep tail when shortening)
    "workflows": ("BY WORKFLOW", "Workflow", "workflows", False),
    "jobs": ("BY JOB", "Job", "jobs", False),
    "repos": ("BY REPO", "Repo", "repos", False),
    "branches": ("BY BRANCH", "Branch", "branches", True),
    "events": ("BY EVENT", "Event", "events", False),
}


def _signed_money(x: float) -> str:
    if round(x, 2) == 0:
        return "$0.00"
    return f"{'+' if x > 0 else '-'}${abs(x):,.2f}"


def _signed_min(x: float) -> str:
    if round(x) == 0:
        return "0"
    return f"{x:+,.0f}"


def _pct_cell(d) -> str:
    """Percent change in cost, or a word when a percentage would be meaningless."""
    if d.status == "new":
        return "new"
    if d.status == "gone":
        return "gone"
    p = d.cost_pct
    if p is None:  # it ran before, but cost $0 (self-hosted, or free) — no percentage of zero
        return "from $0" if round(d.current.cost, 2) > 0 else "–"
    if round(p, 1) == 0:
        return "0.0%"
    return f"{p:+,.0f}%" if abs(p) >= 1000 else f"{p:+.1f}%"


def _period_words(c) -> Tuple[str, str]:
    """('last 7 days', 'the 7 days before') for --days; ('since 2026-09-01', 'the 25.4 days before') else."""
    n = c.days
    if n is not None:
        unit = "day" if n == 1 else "days"
        return f"last {n} {unit}", f"the {n} {unit} before"
    days = c.current_window.days
    span = f"{days:.0f}" if abs(days - round(days)) < 0.05 else f"{days:.1f}"
    return f"since {c.current_window.start:%Y-%m-%d}", f"the {span} days before"


def _when(w) -> str:
    return f"{w.start:%Y-%m-%d %H:%M} → {w.end:%Y-%m-%d %H:%M} UTC"


def _cmp_sections(c, by: Sequence[str]) -> List[str]:
    main = ["repos"] if c.is_org else ["workflows", "jobs"]
    extra = [{"branch": "branches", "event": "events"}[g] for g in by]
    # workflows, then the --by breakdowns, then jobs (same order as the plain report)
    return main[:1] + extra + main[1:]


def _leader(c) -> str:
    """One sentence naming the biggest increase, so the answer is above the fold."""
    key = "repos" if c.is_org else "workflows"
    noun = "repo" if c.is_org else "workflow"
    rows = [d for d in c.sections[key] if round(d.cost_delta, 2) > 0]
    if not rows:
        return f"No {noun} got more expensive."
    d = rows[0]
    s = f"Biggest increase: {d.key} {_signed_money(d.cost_delta)} ({_pct_word(d)})"
    if not c.is_org:
        jobs = [j for j in c.sections["jobs"] if j.key.startswith(d.key + " › ") and round(j.cost_delta, 2) > 0]
        if jobs:
            j = jobs[0]
            s += f", led by {j.key.split(' › ', 1)[1]} {_signed_money(j.cost_delta)} ({_pct_word(j)})"
    return s + "."


def _pct_word(d) -> str:
    cell = _pct_cell(d)
    return {"new": "new", "from $0": "was $0"}.get(cell, cell)


def _total_pct(t) -> str:
    """The total's percent change; empty when flat, 'new' when nothing billed before (no divide by zero)."""
    p = t.cost_pct
    if p is None:
        return "new" if round(t.current.cost, 2) > 0 else ""
    if round(p, 1) == 0:
        return ""
    return f"{p:+,.0f}%" if abs(p) >= 1000 else f"{p:+.1f}%"


def _warnings(c) -> List[str]:
    out = []
    if c.previous.truncated:
        out.append("previous window hit --max-runs: its oldest runs are missing, so increases are overstated.")
    if c.current.truncated:
        out.append("current window hit --max-runs: totals cover only its newest runs.")
    return out


def _cmp_head(title: str, w: int = CMP_W) -> str:
    return (f"  {title:<{w + 1}} {'min before':>10} {'min now':>9}  {'cost before':>11} {'cost now':>10}"
            f"  {'Δ cost':>10} {'Δ %':>8}")


def _cmp_row(d, middle: bool = False, w: int = CMP_W) -> str:
    before_min = "–" if d.status == "new" else f"{d.previous.billed_minutes:,.0f}"
    now_min = "–" if d.status == "gone" else f"{d.current.billed_minutes:,.0f}"
    before = "–" if d.status == "new" else _money(d.previous.cost)
    now = "–" if d.status == "gone" else _money(d.current.cost)
    return (f"  {_fit(d.key, middle, w):<{w + 1}} {before_min:>10} {now_min:>9}  {before:>11} {now:>10}"
            f"  {_signed_money(d.cost_delta):>10} {_pct_cell(d):>8}")


def compare_text(c, top: int = 10, by: Sequence[str] = ()) -> str:
    now_words, before_words = _period_words(c)
    who = f"org {c.subject}" if c.is_org else c.subject
    cur, prev = c.current, c.previous
    t = c.total
    out = [f"runbill · {who} · {now_words} vs {before_words}", ""]
    rw = max(len(f"{prev.run_count:,}"), len(f"{cur.run_count:,}"))
    out.append(f"  now     {_when(c.current_window)}   {cur.run_count:>{rw},} runs")
    out.append(f"  before  {_when(c.previous_window)}   {prev.run_count:>{rw},} runs")
    out.append("")
    pct = _total_pct(t)
    pct = f" ({pct})" if pct else ""
    out.append(f"  TOTAL   {_money(prev.total.cost)} → {_money(cur.total.cost)}   "
               f"{_signed_money(t.cost_delta)}{pct}   billed min {prev.total.billed_minutes:,.0f} → "
               f"{cur.total.billed_minutes:,.0f} ({_signed_min(t.minutes_delta)})")
    out.append(f"  {_leader(c)}")
    out.append("")
    tables = []
    for key in _cmp_sections(c, by):
        title, _, noun, middle = _CMP_SECTIONS[key]
        rows, other = collapse_deltas(c.sections[key], top, noun)
        tables.append((title, middle, rows, other))
    # One name width for every table so the number columns line up down the page: as wide as the longest
    # name shown, between CMP_W and NAME_W (longer names are cut with an ellipsis).
    names = [d.key for _, _, rows, other in tables for d in rows + ([other] if other else [])]
    w = min(NAME_W, max([CMP_W] + [len(n) for n in names]))
    for title, middle, rows, other in tables:
        out.append(_cmp_head(title, w))
        out += [_cmp_row(d, middle, w) for d in rows]
        if other is not None:
            out.append(_cmp_row(other, w=w))
        if not rows:
            out.append("  (no runs in either window)")
        out.append("")
    out += [f"  ! {w}" for w in _warnings(c)]
    out.append("  Sorted by Δ cost, biggest increase first. new = no runs before; gone = no runs now.")
    out.append("  " + (_org_note(cur) if c.is_org else _note(cur)))
    return "\n".join(out)


def _md_cmp_cells(d, g: str = "") -> str:
    before_min = "–" if d.status == "new" else f"{d.previous.billed_minutes:,.0f}"
    now_min = "–" if d.status == "gone" else f"{d.current.billed_minutes:,.0f}"
    before = "–" if d.status == "new" else _money(d.previous.cost)
    now = "–" if d.status == "gone" else _money(d.current.cost)
    pct = _pct_cell(d)
    if d.status in ("new", "gone"):
        pct = f"**{pct}**"
    delta = _signed_money(d.cost_delta)
    if round(d.cost_delta, 2) > 0:
        delta = f"**{delta}**"
    return f"| {_md_name(d.key, g)} | {before_min} | {now_min} | {before} | {now} | {delta} | {pct} |"


def compare_markdown(c, top: int = 10, by: Sequence[str] = ()) -> str:
    now_words, before_words = _period_words(c)
    who = f"org `{c.subject}`" if c.is_org else f"`{c.subject}`"
    cur, prev, t = c.current, c.previous, c.total
    pct = _total_pct(t)
    pct = f", {pct}" if pct else ""
    lines = [f"### runbill · {who} · {now_words} vs {before_words}", "",
             f"**{_money(cur.total.cost)}** vs {_money(prev.total.cost)} before "
             f"(**{_signed_money(t.cost_delta)}{pct}**) · {cur.total.billed_minutes:,.0f} vs "
             f"{prev.total.billed_minutes:,.0f} billed minutes · {cur.run_count} vs {prev.run_count} runs", "",
             f"{_leader(c)}", ""]
    for key in _cmp_sections(c, by):
        _, head, noun, _ = _CMP_SECTIONS[key]
        g = {"branches": "branch", "events": "event"}.get(key, "")
        rows, other = collapse_deltas(c.sections[key], top, noun)
        lines += [f"| {head} | Billed min before | Billed min now | Cost before | Cost now | Δ cost | Δ % |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        lines += [_md_cmp_cells(d, g) for d in rows]
        if other is not None:
            lines.append(_md_cmp_cells(other).replace(f"| {_md_name(other.key)} |", f"| _{other.key}_ |", 1))
        lines.append("")
    lines.append(f"<sub>Now: {_when(c.current_window)} · before: {_when(c.previous_window)} · "
                 "sorted by Δ cost, biggest increase first · new = no runs before, gone = no runs now</sub>")
    lines.append("")
    note = _org_note(cur) if c.is_org else _note(cur)
    lines.append(f"_{note}_")
    lines += [f"_{w[0].upper() + w[1:]}_" for w in _warnings(c)]
    return "\n".join(lines) + "\n"


def compare_json(c, by: Sequence[str] = ()) -> str:
    return json.dumps(c.as_dict(by), indent=2, ensure_ascii=False)


_CMP_CSV_HEAD = ["level", "name", "status", "runs_before", "runs_now", "jobs_before", "jobs_now",
                 "billed_minutes_before", "billed_minutes_now", "cost_usd_before", "cost_usd_now",
                 "delta_billed_minutes", "delta_cost_usd", "delta_cost_pct"]


def compare_csv(c, by: Sequence[str] = ()) -> str:
    """Every row (no 'other' folding), one level per section, plus a `total` row first."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_CMP_CSV_HEAD)
    level = {"workflows": "workflow", "jobs": "job", "repos": "repo", "branches": "branch", "events": "event"}
    sections = [("total", [c.total])] + [(level[k], c.sections[k]) for k in _cmp_sections(c, by)]
    for lvl, rows in sections:
        for d in rows:
            x = d.as_dict()
            p, n, dd = x["previous"], x["current"], x["delta"]
            w.writerow([lvl, x["name"], x["status"], p["runs"], n["runs"], p["jobs"], n["jobs"],
                        p["billed_minutes"], n["billed_minutes"], p["cost_usd"], n["cost_usd"],
                        dd["billed_minutes"], dd["cost_usd"], "" if dd["cost_pct"] is None else dd["cost_pct"]])
    return buf.getvalue()
