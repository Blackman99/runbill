"""Deterministic offline sample data for `runbill demo`."""
from datetime import datetime, timedelta, timezone


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def sample():
    base = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    specs = [  # workflow, [(job, labels, seconds)], count, rerun_every
        ("CI", [("test (ubuntu)", ["ubuntu-latest"], 250), ("test (macos)", ["macos-14"], 410),
                ("test (windows)", ["windows-latest"], 380), ("lint", ["ubuntu-latest"], 35)], 60, 6),
        ("E2E nightly", [("playwright", ["ubuntu-latest-8-cores"], 1260)], 9, 0),
        ("Docs", [("build", ["ubuntu-latest"], 70)], 25, 0),
        ("Release", [("publish", ["ubuntu-latest"], 140), ("sign", ["self-hosted", "linux"], 300)], 3, 0),
    ]
    runs, jobs = [], {}
    rid = 1000
    for wname, js, count, rerun_every in specs:
        for i in range(count):
            rid += 1
            t0 = base + timedelta(hours=i * 3)
            attempts = 2 if rerun_every and i % rerun_every == 0 else 1
            runs.append({"id": rid, "name": wname, "status": "completed", "run_attempt": attempts})
            lst = []
            for a in range(1, attempts + 1):
                for jn, labels, secs in js:
                    s = t0 + timedelta(minutes=30 * (a - 1))
                    lst.append({"name": jn, "labels": labels, "run_attempt": a, "conclusion": "success",
                                "started_at": _iso(s), "completed_at": _iso(s + timedelta(seconds=secs + i % 7))})
            jobs[rid] = lst
    return runs, jobs
