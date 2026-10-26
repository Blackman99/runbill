"""Period-over-period diff (`--compare`): the current window against the one just before it.

Pure functions over runs and Reports, like core.py. The CLI fetches runs once from the start of the
previous window, `split_runs` files each run under the window its `created_at` falls in, and each window
becomes an ordinary Report (same per-job round-up and tariffs), so the two sides are billed identically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .core import Line, OrgReport, Report, parse_time


@dataclass
class Window:
    start: datetime
    end: datetime

    @property
    def days(self) -> float:
        return (self.end - self.start).total_seconds() / 86400.0

    def as_dict(self) -> dict:
        return {"from": _iso(self.start), "to": _iso(self.end), "days": round(self.days, 2)}


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compare_windows(now: datetime, days: int = 30, since: Optional[str] = None) -> Tuple[Window, Window]:
    """(previous, current): two back-to-back windows of exactly equal length, the current one ending now.

    `--days N` means the last N x 24 hours; `--since YYYY-MM-DD` starts at 00:00 UTC that day. The previous
    window is the same length again, ending where the current one starts.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if since:
        try:
            start = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError(f"--since {since!r} is not a date like 2026-09-01") from None
    else:
        if days < 1:
            raise ValueError("--days must be 1 or more")
        start = now - timedelta(days=days)
    if start >= now:
        raise ValueError(f"--since {since} is not in the past, so there is no window to compare")
    length = now - start
    return Window(start - length, start), Window(start, now)


def split_runs(runs: Iterable[dict], previous: Window, current: Window,
               max_runs: int) -> Tuple[List[dict], List[dict], bool, bool]:
    """File runs (newest first, as the API returns them) under the previous or current window.

    `runs` should come from one fetch capped at 2 * max_runs + 1 starting at previous.start's date.
    Returns (previous_runs, current_runs, previous_truncated, current_truncated); each side keeps at most
    `max_runs` runs. Runs older than the previous window (the fetch starts at midnight) are dropped; a run
    without `created_at` is counted in the current window.

    The previous side is only complete if the fetch reached past its start (saw an older run) or ran out of
    runs before the cap. Otherwise its oldest runs are missing, which would overstate any increase, so it is
    flagged as truncated.
    """
    runs = list(runs)
    cap = 2 * max_runs
    hit_cap = len(runs) > cap
    runs = runs[:cap]
    prev: List[dict] = []
    cur: List[dict] = []
    reached_older = False
    for r in runs:
        t = parse_time(r.get("created_at"))
        if t is None or t >= current.start:
            cur.append(r)
        elif t >= previous.start:
            prev.append(r)
        else:
            reached_older = True
    cur_trunc = len(cur) > max_runs
    prev_trunc = len(prev) > max_runs or (hit_cap and not reached_older)
    return prev[:max_runs], cur[:max_runs], prev_trunc, cur_trunc


@dataclass
class Delta:
    """One row of a diff: the same workflow / job / repo / branch / event in both windows."""
    key: str
    previous: Line
    current: Line
    in_previous: bool
    in_current: bool

    @property
    def cost_delta(self) -> float:
        return self.current.cost - self.previous.cost

    @property
    def minutes_delta(self) -> float:
        return self.current.billed_minutes - self.previous.billed_minutes

    @property
    def cost_pct(self) -> Optional[float]:
        """Percent change in cost, or None when the previous cost was $0 (no divide by zero)."""
        if self.previous.cost <= 0:
            return None
        return self.cost_delta / self.previous.cost * 100.0

    @property
    def status(self) -> str:
        """new (no runs before), gone (no runs now), up, down or flat (by cost, to the cent)."""
        if not self.in_previous and self.in_current:
            return "new"
        if self.in_previous and not self.in_current:
            return "gone"
        d = round(self.cost_delta, 2)
        return "up" if d > 0 else "down" if d < 0 else "flat"

    def absorb(self, other: "Delta") -> None:
        self.previous.absorb(other.previous)
        self.current.absorb(other.current)
        self.in_previous = self.in_previous or other.in_previous
        self.in_current = self.in_current or other.in_current

    def as_dict(self) -> dict:
        def side(x: Line) -> dict:
            return {"runs": x.runs, "jobs": x.jobs, "billed_minutes": round(x.billed_minutes, 2),
                    "cost_usd": round(x.cost, 4)}
        pct = self.cost_pct
        return {
            "name": self.key, "status": self.status,
            "previous": side(self.previous), "current": side(self.current),
            "delta": {"runs": self.current.runs - self.previous.runs,
                      "jobs": self.current.jobs - self.previous.jobs,
                      "billed_minutes": round(self.minutes_delta, 2),
                      "cost_usd": round(self.cost_delta, 4),
                      "cost_pct": None if pct is None else round(pct, 2)},
        }


def _present(x: Line) -> bool:
    # Job lines carry runs = 0, so a job is present if it billed anything; a workflow if it ran at all.
    return x.runs > 0 or x.jobs > 0


def diff_lines(previous: Sequence[Line], current: Sequence[Line]) -> List[Delta]:
    """Pair lines by key and rank by cost change: biggest increase first, biggest drop last."""
    p = {x.key: x for x in previous}
    c = {x.key: x for x in current}
    out = []
    for key in list(c) + [k for k in p if k not in c]:
        a, b = p.get(key), c.get(key)
        out.append(Delta(key, _copy(a, key), _copy(b, key), a is not None and _present(a),
                         b is not None and _present(b)))
    return sorted(out, key=lambda d: (-round(d.cost_delta, 6), -d.current.cost, -d.minutes_delta, d.key))


def _copy(x: Optional[Line], key: str) -> Line:
    out = Line(key)
    if x is not None:
        out.absorb(x)
    return out


def collapse_deltas(rows: Sequence[Delta], top: int, noun: str) -> Tuple[List[Delta], Optional[Delta]]:
    """First `top` rows plus one 'N other <noun>' row summing the rest, so a table still adds up."""
    rows = list(rows)
    top = max(1, top)
    if len(rows) <= top + 1:
        return rows, None
    rest = rows[top:]
    label = f"{len(rest)} other {noun}"
    # New and gone rows are the point of a diff; when some are folded away, say how many.
    marks = [f"{n} {s}" for s in ("new", "gone") for n in [sum(d.status == s for d in rest)] if n]
    if marks:
        label += f" ({', '.join(marks)})"
    other = Delta(label, Line(label), Line(label), False, False)
    for d in rest:
        other.absorb(d)
    return rows[:top], other


AnyReport = Union[Report, OrgReport]
SECTION_KEYS = ("workflows", "jobs", "repos", "branches", "events")


@dataclass
class Comparison:
    previous: AnyReport
    current: AnyReport
    previous_window: Window
    current_window: Window
    days: Optional[int] = None  # N for --days N (for the "last N days" header); None for --since
    total: Delta = None  # type: ignore[assignment]
    sections: Dict[str, List[Delta]] = field(default_factory=dict)

    @property
    def is_org(self) -> bool:
        return isinstance(self.current, OrgReport)

    @property
    def subject(self) -> str:
        return self.current.org if isinstance(self.current, OrgReport) else self.current.repo

    def as_dict(self, by: Sequence[str] = ()) -> dict:
        def period(rep: AnyReport, w: Window) -> dict:
            return {**w.as_dict(), "runs": rep.run_count, "truncated": rep.truncated,
                    "total": rep.total.as_dict()}
        d: dict = {"org" if self.is_org else "repo": self.subject, "private": self.current.private,
                   "compare": {"previous": period(self.previous, self.previous_window),
                               "current": period(self.current, self.current_window)},
                   "total": self.total.as_dict()}
        main = ("repos",) if self.is_org else ("workflows", "jobs")
        for key in main + tuple({"branch": "branches", "event": "events"}[g] for g in by):
            d[key] = [x.as_dict() for x in self.sections[key]]
        return d


def build_comparison(previous: AnyReport, current: AnyReport, previous_window: Window,
                     current_window: Window, days: Optional[int] = None) -> Comparison:
    if type(previous) is not type(current):
        raise TypeError("compare two repo reports or two org reports")
    total = Delta("total", _copy(previous.total, "total"), _copy(current.total, "total"),
                  _present(previous.total), _present(current.total))
    sections: Dict[str, List[Delta]] = {}
    if isinstance(current, OrgReport):
        sections["repos"] = diff_lines(previous.repos, current.repos)  # type: ignore[union-attr]
    else:
        sections["workflows"] = diff_lines(previous.workflows, current.workflows)  # type: ignore[union-attr]
        sections["jobs"] = diff_lines(previous.jobs, current.jobs)  # type: ignore[union-attr]
    sections["branches"] = diff_lines(previous.branches, current.branches)
    sections["events"] = diff_lines(previous.events, current.events)
    return Comparison(previous, current, previous_window, current_window, days, total, sections)


def increase_over(cmp: Comparison, pct: float) -> Tuple[bool, Optional[float]]:
    """For --fail-increase: (is the total cost up by more than pct %?, the actual % or None if prev was $0)."""
    actual = cmp.total.cost_pct
    if actual is None:
        return False, None
    return actual > pct, actual
