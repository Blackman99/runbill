"""Billing math. Pure functions over GitHub API job/run dicts, so they are easy to test."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional

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

    def as_dict(self) -> dict:
        t = self.total
        return {
            "repo": self.repo, "since": self.since, "private": self.private,
            "runs": self.run_count, "truncated": self.truncated,
            "total": t.as_dict(),
            "rerun_share": round(t.rerun_cost / t.cost, 4) if t.cost else 0.0,
            "workflows": [w.as_dict() for w in self.workflows],
            "jobs": [j.as_dict() for j in self.jobs],
        }



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

    def as_dict(self) -> dict:
        t = self.total
        return {
            "org": self.org, "since": self.since, "private": self.private,
            "runs": self.run_count, "truncated": self.truncated,
            "repo_scanned": self.repo_scanned, "repo_active": self.repo_active,
            "public_repos": self.public_repos, "private_repos": self.private_repos,
            "total": t.as_dict(),
            "rerun_share": round(t.rerun_cost / t.cost, 4) if t.cost else 0.0,
            "repos": [r.as_dict() for r in self.repos],
        }


def build_org_report(org: str, since: str, reports: Iterable[Report],
                     repo_scanned: int, truncated: bool = False) -> OrgReport:
    """Aggregate per-repo reports into an org rollup ranked by cost."""
    reports = list(reports)
    total = Line("total")
    lines: List[Line] = []
    public_n = private_n = 0
    privacies: List[Optional[bool]] = []
    for rep in reports:
        privacies.append(rep.private)
        if rep.private is True:
            private_n += 1
        elif rep.private is False:
            public_n += 1
        src = rep.total
        line = Line(rep.repo)
        line.runs = src.runs
        line.jobs = src.jobs
        line.seconds = src.seconds
        line.billed_minutes = src.billed_minutes
        line.cost = src.cost
        line.rerun_cost = src.rerun_cost
        line.by_sku = dict(src.by_sku)
        lines.append(line)
        total.runs += src.runs
        total.jobs += src.jobs
        total.seconds += src.seconds
        total.billed_minutes += src.billed_minutes
        total.cost += src.cost
        total.rerun_cost += src.rerun_cost
        for sku, mins in src.by_sku.items():
            total.by_sku[sku] = total.by_sku.get(sku, 0.0) + mins
    if privacies and all(p is False for p in privacies):
        private: Optional[bool] = False
    elif any(p is True for p in privacies):
        private = True
    else:
        private = None
    any_trunc = truncated or any(r.truncated for r in reports)
    return OrgReport(
        org, since, private, total,
        sorted(lines, key=lambda x: (-x.cost, -x.billed_minutes, x.key)),
        total.runs, repo_scanned, len(lines), any_trunc,
        public_repos=public_n, private_repos=private_n,
    )

def build_report(repo: str, since: str, runs: Iterable[dict], jobs_by_run: Dict[int, List[dict]],
                 rates: Optional[Dict[str, float]] = None, private: Optional[bool] = None,
                 truncated: bool = False) -> Report:
    rates = {**DEFAULT_RATES, **(rates or {})}
    total = Line("total")
    wf: Dict[str, Line] = {}
    jb: Dict[str, Line] = {}
    n = 0
    for run in runs:
        n += 1
        wname = run.get("name") or run.get("path") or str(run.get("workflow_id"))
        w = wf.setdefault(wname, Line(wname))
        w.runs += 1
        total.runs += 1
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
            for line in (total, w, j):
                line.jobs += 1
                line.seconds += secs
                line.billed_minutes += billed
                line.cost += cost
                if rerun:
                    line.rerun_cost += cost
                line.by_sku[sku] = line.by_sku.get(sku, 0.0) + billed
    j_sorted = sorted(jb.values(), key=lambda x: (-x.cost, -x.billed_minutes, x.key))
    for j in j_sorted:
        j.runs = 0
    return Report(repo, since, private, total,
                  sorted(wf.values(), key=lambda x: (-x.cost, -x.billed_minutes, x.key)),
                  j_sorted, n, truncated)
