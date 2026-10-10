"""Billing math. Pure functions over GitHub API job/run dicts, so they are easy to test."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional

# USD per minute for GitHub-hosted standard runners (list price, 2-core Linux/Windows,
# 3/4-core macOS). Override with --rate os=price. Check https://docs.github.com/billing.
DEFAULT_RATES: Dict[str, float] = {
    "linux": 0.006,
    "linux-arm": 0.005,
    "windows": 0.010,
    "windows-arm": 0.010,
    "macos": 0.062,
    "self-hosted": 0.0,
}

_CORES = re.compile(r"(\d+)[-_]?(?:core|cores|cpu|vcpu)\b", re.I)


def parse_time(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def classify_runner(job: dict) -> tuple:
    """Return (sku, multiplier) for a job, e.g. ("linux", 1.0) or ("linux", 4.0) for 8-core."""
    labels = [str(x).lower() for x in (job.get("labels") or [])]
    group = (job.get("runner_group_name") or "").lower()
    name = (job.get("runner_name") or "").lower()
    joined = " ".join(labels)
    if "self-hosted" in labels or (group and group not in ("github actions", "default", "")
                                   and not name.startswith("github actions")
                                   and not any(re.match(r"(ubuntu|windows|macos)", x) for x in labels)):
        return "self-hosted", 1.0
    if "macos" in joined or "mac" in labels:
        return "macos", 1.0
    arm = "arm" in joined
    if "windows" in joined:
        sku = "windows-arm" if arm else "windows"
    else:
        sku = "linux-arm" if arm else "linux"
    mult = 1.0
    m = _CORES.search(joined)
    if m:
        mult = max(1.0, int(m.group(1)) / 2.0)
    return sku, mult


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
    billed_minutes: float = 0.0  # rounded up per job, times size multiplier
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
