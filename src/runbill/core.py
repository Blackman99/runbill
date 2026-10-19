"""Billing math. Pure functions over GitHub API job/run dicts, so they are easy to test."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# USD per minute at GitHub list price, from the Actions runner pricing reference:
# https://docs.github.com/en/billing/reference/actions-runner-pricing (checked 2026-10-10).
# Keys are runbill SKU names (GitHub billing SKU in the comment). Override with --rate SKU=price.
DEFAULT_RATES: Dict[str, float] = {
    # standard runners
    "linux": 0.006,              # actions_linux (2-core x64)
    "linux-slim": 0.002,         # actions_linux_slim (1-core x64, label ubuntu-slim)
    "linux-arm": 0.005,          # actions_linux_arm (2-core arm64)
    "windows": 0.010,            # actions_windows (2-core x64)
    "windows-arm": 0.010,        # actions_windows_arm (2-core arm64)
    "macos": 0.062,              # actions_macos (3/4-core)
    # x64 larger runners
    "linux-4-core": 0.012,       # linux_4_core
    "linux-8-core": 0.022,       # linux_8_core
    "linux-16-core": 0.042,      # linux_16_core
    "linux-32-core": 0.082,      # linux_32_core
    "linux-64-core": 0.162,      # linux_64_core
    "linux-96-core": 0.252,      # linux_96_core
    "windows-4-core": 0.022,     # windows_4_core
    "windows-8-core": 0.042,     # windows_8_core
    "windows-16-core": 0.082,    # windows_16_core
    "windows-32-core": 0.162,    # windows_32_core
    "windows-64-core": 0.322,    # windows_64_core
    "windows-96-core": 0.552,    # windows_96_core
    "macos-large": 0.077,        # macos_l (12-core Intel, labels macos-*-large)
    "macos-xlarge": 0.102,       # macos_xl (5-core M2 Pro, labels macos-*-xlarge)
    # arm64 larger runners
    "linux-arm-4-core": 0.008,   # linux_4_core_arm
    "linux-arm-8-core": 0.014,   # linux_8_core_arm
    "linux-arm-16-core": 0.026,  # linux_16_core_arm
    "linux-arm-32-core": 0.050,  # linux_32_core_arm
    "linux-arm-64-core": 0.098,  # linux_64_core_arm
    "windows-arm-2-core": 0.008,   # windows_2_core_arm
    "windows-arm-4-core": 0.014,   # windows_4_core_arm
    "windows-arm-8-core": 0.026,   # windows_8_core_arm
    "windows-arm-16-core": 0.050,  # windows_16_core_arm
    "windows-arm-32-core": 0.098,  # windows_32_core_arm
    "windows-arm-64-core": 0.194,  # windows_64_core_arm
    # GPU larger runners
    "linux-gpu": 0.052,          # linux_4_core_gpu
    "windows-gpu": 0.102,        # windows_4_core_gpu
    # not billed by GitHub
    "self-hosted": 0.0,
}

_CORES = re.compile(r"(\d+)[-_]?(?:core|cores|cpu|cpus|vcpu|vcpus)\b", re.I)


def parse_time(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def classify_runner(job: dict) -> tuple:
    """Return (sku, multiplier) for a job.

    The SKU is a key of DEFAULT_RATES, e.g. ("linux", 1.0), ("linux-8-core", 1.0), ("macos-xlarge", 1.0).
    Larger runners get GitHub's published per-size rate. Only a core count with no published row
    (e.g. a 12-core Linux label) falls back to the base SKU times cores/2.
    """
    labels = [str(x).lower() for x in (job.get("labels") or [])]
    group = (job.get("runner_group_name") or "").lower()
    name = (job.get("runner_name") or "").lower()
    joined = " ".join(labels)
    if "self-hosted" in labels or (group and group not in ("github actions", "default", "")
                                   and not name.startswith("github actions")
                                   and not any(re.match(r"(ubuntu|windows|macos|xcode)", x) for x in labels)):
        return "self-hosted", 1.0
    if "macos" in joined or "mac" in labels or any(x.startswith("xcode-") for x in labels):
        if re.search(r"(^|[-_ ])xlarge\b", joined):
            return "macos-xlarge", 1.0
        if re.search(r"(^|[-_ ])large\b", joined):
            return "macos-large", 1.0
        return "macos", 1.0
    if "ubuntu-slim" in labels:
        return "linux-slim", 1.0
    arm = "arm" in joined
    os_ = "windows" if "windows" in joined else "linux"
    base = f"{os_}-arm" if arm else os_
    if "gpu" in joined:
        return f"{os_}-gpu", 1.0
    m = _CORES.search(joined)
    if not m:
        return base, 1.0
    cores = int(m.group(1))
    if cores == 1 and os_ == "linux" and not arm:
        return "linux-slim", 1.0
    if cores <= 2 and not (os_ == "windows" and arm):
        return base, 1.0  # 2-core larger runners cost the same as standard ones
    sized = f"{base}-{cores}-core"
    if sized in DEFAULT_RATES:
        return sized, 1.0
    return base, max(1.0, cores / 2.0)


def job_seconds(job: dict) -> float:
    a, b = parse_time(job.get("started_at")), parse_time(job.get("completed_at"))
    if not a or not b:
        return 0.0
    return max(0.0, (b - a).total_seconds())


# Breakdowns `--by` can add to a report, and the run field each one groups on.
GROUPINGS = ("branch", "event")
NO_BRANCH = "(no branch)"
UNKNOWN_EVENT = "(unknown event)"


def branch_key(run: dict) -> str:
    """The branch a run is billed to: its head branch, as GitHub shows it.

    A pull request from a fork reports the fork's branch name (often `main`); it is shown as
    `owner:branch`, the way GitHub's PR header does, so fork PRs never inflate your own `main`.
    """
    br = run.get("head_branch")
    if not br:
        return NO_BRANCH
    head = (run.get("head_repository") or {}).get("full_name") or ""
    base = (run.get("repository") or {}).get("full_name") or ""
    if head and base and head.lower() != base.lower():
        return f"{head.split('/')[0]}:{br}"
    return br


def event_key(run: dict) -> str:
    """The trigger of a run (push, pull_request, schedule, workflow_dispatch, merge_group, ...).

    Any event string GitHub sends is kept as-is, so new or rare triggers show up under their own name.
    """
    return run.get("event") or UNKNOWN_EVENT


@dataclass
class Line:
    key: str
    runs: int = 0
    jobs: int = 0
    seconds: float = 0.0
    billed_minutes: float = 0.0  # rounded up per job (times a fallback size multiplier, if any)
    cost: float = 0.0
    rerun_cost: float = 0.0
    by_sku: Dict[str, float] = field(default_factory=dict)

    def absorb(self, other: "Line") -> None:
        """Add another line's counts to this one (used for roll-ups and 'other N' rows)."""
        self.runs += other.runs
        self.jobs += other.jobs
        self.seconds += other.seconds
        self.billed_minutes += other.billed_minutes
        self.cost += other.cost
        self.rerun_cost += other.rerun_cost
        for sku, mins in other.by_sku.items():
            self.by_sku[sku] = self.by_sku.get(sku, 0.0) + mins

    def as_dict(self) -> dict:
        return {
            "name": self.key, "runs": self.runs, "jobs": self.jobs,
            "raw_minutes": round(self.seconds / 60.0, 2),
            "billed_minutes": round(self.billed_minutes, 2),
            "cost_usd": round(self.cost, 4), "rerun_cost_usd": round(self.rerun_cost, 4),
            "billed_minutes_by_runner": {k: round(v, 2) for k, v in sorted(self.by_sku.items())},
        }


@dataclass
class Report:
    repo: str
    since: str
    private: Optional[bool]
    total: Line
    workflows: List[Line]
    jobs: List[Line]
    run_count: int
    truncated: bool = False
    branches: List[Line] = field(default_factory=list)  # ranked by cost; see branch_key
    events: List[Line] = field(default_factory=list)    # ranked by cost; see event_key

    def groups(self, by: str) -> List[Line]:
        return {"branch": self.branches, "event": self.events}[by]

    def as_dict(self, by: Sequence[str] = ()) -> dict:
        t = self.total
        d = {
            "repo": self.repo, "since": self.since, "private": self.private,
            "runs": self.run_count, "truncated": self.truncated,
            "total": t.as_dict(),
            "rerun_share": round(t.rerun_cost / t.cost, 4) if t.cost else 0.0,
            "workflows": [w.as_dict() for w in self.workflows],
            "jobs": [j.as_dict() for j in self.jobs],
        }
        _add_groups(d, self, by)
        return d



@dataclass
class OrgReport:
    """Roll-up of per-repo Report totals for an org or user."""
    org: str
    since: str
    private: Optional[bool]
    total: Line
    repos: List[Line]  # ranked by cost descending; key is OWNER/REPO
    run_count: int
    repo_scanned: int
    repo_active: int
    truncated: bool = False
    public_repos: int = 0
    private_repos: int = 0
    branches: List[Line] = field(default_factory=list)  # key "repo › branch"
    events: List[Line] = field(default_factory=list)    # summed across repos

    def groups(self, by: str) -> List[Line]:
        return {"branch": self.branches, "event": self.events}[by]

    def as_dict(self, by: Sequence[str] = ()) -> dict:
        t = self.total
        d = {
            "org": self.org, "since": self.since, "private": self.private,
            "runs": self.run_count, "truncated": self.truncated,
            "repo_scanned": self.repo_scanned, "repo_active": self.repo_active,
            "public_repos": self.public_repos, "private_repos": self.private_repos,
            "total": t.as_dict(),
            "rerun_share": round(t.rerun_cost / t.cost, 4) if t.cost else 0.0,
            "repos": [r.as_dict() for r in self.repos],
        }
        _add_groups(d, self, by)
        return d


_JSON_KEY = {"branch": "branches", "event": "events"}


def _add_groups(d: dict, rep, by: Sequence[str]) -> None:
    for g in by:
        d[_JSON_KEY[g]] = [x.as_dict() for x in rep.groups(g)]


def _ranked(lines: Iterable[Line]) -> List[Line]:
    return sorted(lines, key=lambda x: (-x.cost, -x.billed_minutes, x.key))


def collapse(lines: Sequence[Line], top: int, noun: str) -> Tuple[List[Line], Optional[Line]]:
    """Split ranked lines into the first `top` rows plus one 'N other <noun>' row for the rest.

    `noun` is the plural ("branches", "events").

    The shown rows plus the other row always add up to the full list, so a table never loses money.
    A tail of a single line is shown as itself (a row saying '1 other branch' tells you less).
    """
    lines = list(lines)
    top = max(1, top)
    if len(lines) <= top + 1:
        return lines, None
    rest = lines[top:]
    other = Line(f"{len(rest)} other {noun}")
    for x in rest:
        other.absorb(x)
    return lines[:top], other


def build_org_report(org: str, since: str, reports: Iterable[Report],
                     repo_scanned: int, truncated: bool = False) -> OrgReport:
    """Aggregate per-repo reports into an org rollup ranked by cost."""
    reports = list(reports)
    total = Line("total")
    lines: List[Line] = []
    branches: Dict[str, Line] = {}
    events: Dict[str, Line] = {}
    public_n = private_n = 0
    privacies: List[Optional[bool]] = []
    for rep in reports:
        privacies.append(rep.private)
        if rep.private is True:
            private_n += 1
        elif rep.private is False:
            public_n += 1
        line = Line(rep.repo)
        line.absorb(rep.total)
        lines.append(line)
        total.absorb(rep.total)
        short = rep.repo.split("/", 1)[-1]
        for b in rep.branches:
            key = f"{short} › {b.key}"
            branches.setdefault(key, Line(key)).absorb(b)
        for e in rep.events:
            events.setdefault(e.key, Line(e.key)).absorb(e)
    if privacies and all(p is False for p in privacies):
        private: Optional[bool] = False
    elif any(p is True for p in privacies):
        private = True
    else:
        private = None
    any_trunc = truncated or any(r.truncated for r in reports)
    return OrgReport(
        org, since, private, total, _ranked(lines),
        total.runs, repo_scanned, len(lines), any_trunc,
        public_repos=public_n, private_repos=private_n,
        branches=_ranked(branches.values()), events=_ranked(events.values()),
    )


def build_report(repo: str, since: str, runs: Iterable[dict], jobs_by_run: Dict[int, List[dict]],
                 rates: Optional[Dict[str, float]] = None, private: Optional[bool] = None,
                 truncated: bool = False) -> Report:
    rates = {**DEFAULT_RATES, **(rates or {})}
    total = Line("total")
    wf: Dict[str, Line] = {}
    jb: Dict[str, Line] = {}
    br: Dict[str, Line] = {}
    ev: Dict[str, Line] = {}
    n = 0
    for run in runs:
        n += 1
        wname = run.get("name") or run.get("path") or str(run.get("workflow_id"))
        w = wf.setdefault(wname, Line(wname))
        bkey, ekey = branch_key(run), event_key(run)
        b = br.setdefault(bkey, Line(bkey))
        e = ev.setdefault(ekey, Line(ekey))
        for line in (total, w, b, e):
            line.runs += 1
        for job in jobs_by_run.get(run["id"], []):
            if job.get("conclusion") == "skipped":
                continue
            secs = job_seconds(job)
            if secs <= 0:
                continue
            sku, mult = classify_runner(job)
            billed = math.ceil(secs / 60.0) * mult
            cost = billed * rates.get(sku, 0.0)
            rerun = (job.get("run_attempt") or 1) > 1
            jkey = f"{wname} › {job.get('name')}"
            j = jb.setdefault(jkey, Line(jkey))
            # Each job's rounded-up minutes land in exactly one workflow, branch and event,
            # so every breakdown adds up to the same total.
            for line in (total, w, j, b, e):
                line.jobs += 1
                line.seconds += secs
                line.billed_minutes += billed
                line.cost += cost
                if rerun:
                    line.rerun_cost += cost
                line.by_sku[sku] = line.by_sku.get(sku, 0.0) + billed
    j_sorted = _ranked(jb.values())
    for j in j_sorted:
        j.runs = 0
    return Report(repo, since, private, total, _ranked(wf.values()), j_sorted, n, truncated,
                  branches=_ranked(br.values()), events=_ranked(ev.values()))
