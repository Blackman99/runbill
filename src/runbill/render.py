"""Text / markdown / JSON / CSV output."""
from __future__ import annotations

import csv
import io
import json

from typing import List, Sequence

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
