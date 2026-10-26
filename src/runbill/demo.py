"""Deterministic offline sample data for `runbill demo`."""
from datetime import datetime, timedelta, timezone

REPO = "example/app"

# Pull-request branches for the CI workflow, with how many CI runs each one triggers: a few busy
# feature branches, a fork PR, bot bumps, and a long tail of one-run branches.
_PR_BRANCHES = [
    ("feat/checkout-v2", 9), ("fix/flaky-login-test", 6), ("octo-contrib/app:main", 4),
    ("dependabot/npm_and_yarn/frontend/esbuild-0.25.10", 3), ("renovate/actions-checkout-5.x", 2),
] + [(b, 1) for b in (
    "feat/dark-mode", "fix/typo-readme", "chore/bump-node-22", "feat/export-csv", "refactor/auth-middleware",
    "fix/timezone-dst", "feat/sso-okta", "perf/cache-warmup", "fix/null-avatar", "feat/billing-page",
    "test/e2e-retry", "chore/eslint-9")]


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _pr_branch_sequence():
    for name, count in _PR_BRANCHES:
        for _ in range(count):
            yield name


def _trigger(wname, i, pr_branches):
    """(event, head_branch, head repo full name) for run i of a workflow."""
    if wname == "CI":
        if i % 3 == 0:
            return "push", "main", REPO
        if i % 10 == 5:
            return "merge_group", f"gh-readonly-queue/main/pr-{400 + i}-{(i * 2654435761) % 16**7:07x}", REPO
        branch = next(pr_branches)
        if ":" in branch:  # fork PR: GitHub reports the fork's own branch name
            fork, branch = branch.split(":", 1)
            return "pull_request", branch, fork
        return "pull_request", branch, REPO
    if wname == "E2E nightly":
        return "schedule", "main", REPO
    if wname == "Docs":
        return ("pull_request", "docs/new-quickstart", REPO) if i % 5 == 0 else ("push", "main", REPO)
    return "workflow_dispatch", "main", REPO


BASE = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)  # start of the demo's current week

# workflow, [(job, labels, seconds)], count, rerun_every
_THIS_WEEK = [
    ("CI", [("test (ubuntu)", ["ubuntu-latest"], 250), ("test (macos)", ["macos-14"], 410),
            ("test (windows)", ["windows-latest"], 380), ("lint", ["ubuntu-latest"], 35)], 60, 6),
    ("E2E nightly", [("playwright", ["ubuntu-latest-8-cores"], 1260)], 9, 0),
    ("Docs", [("build", ["ubuntu-latest"], 70)], 25, 0),
    ("Release", [("publish", ["ubuntu-latest"], 140), ("sign", ["self-hosted", "linux"], 300)], 3, 0),
]

# The week before, for `runbill demo --compare`: no macOS leg in CI yet, E2E still on a standard runner,
# a Benchmarks workflow that was deleted since, a bit more Docs churn, and no release.
_LAST_WEEK = [
    ("CI", [("test (ubuntu)", ["ubuntu-latest"], 250), ("test (windows)", ["windows-latest"], 380),
            ("lint", ["ubuntu-latest"], 35)], 48, 8),
    ("E2E nightly", [("playwright", ["ubuntu-latest"], 1260)], 7, 0),
    ("Docs", [("build", ["ubuntu-latest"], 70)], 31, 0),
    ("Benchmarks", [("bench", ["ubuntu-latest-4-cores"], 840)], 7, 0),
]


def _build(specs, base, rid):
    runs, jobs = [], {}
    pr_branches = _pr_branch_sequence()
    for wname, js, count, rerun_every in specs:
        for i in range(count):
            rid += 1
            t0 = base + timedelta(hours=i * 3)
            # Runs are spread evenly over the week (job timings above stay as they are).
            created = base + timedelta(seconds=i * 7 * 86400 // count)
            attempts = 2 if rerun_every and i % rerun_every == 0 else 1
            event, branch, head_repo = _trigger(wname, i, pr_branches)
            runs.append({"id": rid, "name": wname, "status": "completed", "run_attempt": attempts,
                         "event": event, "head_branch": branch, "created_at": _iso(created),
                         "head_repository": {"full_name": head_repo}, "repository": {"full_name": REPO}})
            lst = []
            for a in range(1, attempts + 1):
                for jn, labels, secs in js:
                    s = t0 + timedelta(minutes=30 * (a - 1))
                    lst.append({"name": jn, "labels": labels, "run_attempt": a, "conclusion": "success",
                                "started_at": _iso(s), "completed_at": _iso(s + timedelta(seconds=secs + i % 7))})
            jobs[rid] = lst
    return runs, jobs


def sample():
    """One week of runs from BASE: (runs, jobs_by_run_id)."""
    return _build(_THIS_WEEK, BASE, 1000)


def sample_two_weeks():
    """Two back-to-back weeks for `demo --compare`, newest run first like the API: (runs, jobs, now)."""
    cur_runs, cur_jobs = sample()
    prev_runs, prev_jobs = _build(_LAST_WEEK, BASE - timedelta(days=7), 5000)
    runs = sorted(cur_runs + prev_runs, key=lambda r: r["created_at"], reverse=True)
    return runs, {**cur_jobs, **prev_jobs}, BASE + timedelta(days=7)
