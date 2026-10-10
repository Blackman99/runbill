"""runbill command line."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import __version__, render
from .core import DEFAULT_RATES, build_report
from .github import Client, GitHubError, find_token


def _detect_repo() -> "str | None":
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True,
                             timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else None


def _rates(items):
    out = {}
    for it in items or []:
        k, _, v = it.partition("=")
        if k not in DEFAULT_RATES or not v:
            raise SystemExit(f"runbill: bad --rate {it!r}; keys: {', '.join(DEFAULT_RATES)}")
        out[k] = float(v)
    return out


def _emit(report, fmt, top, out):
    s = {"text": lambda: render.text(report, top), "md": lambda: render.markdown(report, top),
         "json": lambda: render.as_json(report), "csv": lambda: render.as_csv(report)}[fmt]()
    if out:
        with open(out, "a" if out == os.environ.get("GITHUB_STEP_SUMMARY") else "w", encoding="utf-8") as f:
            f.write(s if s.endswith("\n") else s + "\n")
    else:
        print(s)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="runbill", description="Which GitHub Actions workflow and job is eating "
                                "your minutes? Per-workflow/per-job billed minutes and cost from the runs API.")
    p.add_argument("--version", action="version", version=f"runbill {__version__}")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("report", help="report on a repository (default command)")
    r.add_argument("repo", nargs="?", help="OWNER/REPO (default: GITHUB_REPOSITORY or git origin)")
    r.add_argument("--days", type=int, default=30, help="look back N days (default 30)")
    r.add_argument("--since", help="start date YYYY-MM-DD (overrides --days)")
    r.add_argument("--workflow", help="only this workflow (file name like ci.yml, or id)")
    r.add_argument("--branch", help="only runs on this branch")
    r.add_argument("--max-runs", type=int, default=500, help="stop after N runs (default 500)")
    r.add_argument("--top", type=int, default=10, help="rows per table (default 10)")
    r.add_argument("--rate", action="append", metavar="SKU=USD", help="override $/min, e.g. macos=0.08")
    r.add_argument("--format", choices=["text", "md", "json", "csv"], default="text")
    r.add_argument("--output", "-o", help="write to file instead of stdout")
    r.add_argument("--fail-over", type=float, metavar="USD", help="exit 3 if total cost exceeds USD")
    d = sub.add_parser("demo", help="offline sample report (no network)")
    d.add_argument("--format", choices=["text", "md", "json", "csv"], default="text")
    sub.add_parser("rates", help="print the default $/min table")

    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ("report", "demo", "rates", "-h", "--help", "--version"):
        argv.insert(0, "report")
    a = p.parse_args(argv)
    if a.cmd is None:
        p.print_help()
        return 0
    if a.cmd == "rates":
        for k, v in DEFAULT_RATES.items():
            print(f"{k:<12} ${v:.3f}/min")
        return 0
    if a.cmd == "demo":
        from .demo import sample
        runs, jobs = sample()
        rep = build_report("example/app", "2026-10-01", runs, jobs, private=True)
        _emit(rep, a.format, 10, None)
        return 0

    repo = a.repo or _detect_repo()
    if not repo or "/" not in repo:
        print("runbill: give OWNER/REPO (could not detect it from git origin)", file=sys.stderr)
        return 2
    since = a.since or (datetime.now(timezone.utc) - timedelta(days=a.days)).strftime("%Y-%m-%d")
    cli = Client(find_token())
    try:
        meta = cli.repo(repo)
        runs = list(cli.runs(repo, since, a.max_runs + 1, a.workflow, a.branch))
        truncated = len(runs) > a.max_runs
        runs = runs[: a.max_runs]
        print(f"runbill: fetching jobs for {len(runs)} runs…", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=8) as ex:
            jobs = dict(zip([x["id"] for x in runs], ex.map(lambda x: cli.jobs(repo, x["id"]), runs)))
    except GitHubError as e:
        print(f"runbill: {e}", file=sys.stderr)
        return 1
    rep = build_report(repo, since, runs, jobs, _rates(a.rate), private=meta.get("private"),
                       truncated=truncated)
    _emit(rep, a.format, a.top, a.output)
    if a.fail_over is not None and rep.total.cost > a.fail_over:
        print(f"runbill: total ${rep.total.cost:.2f} is over --fail-over ${a.fail_over:.2f}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
