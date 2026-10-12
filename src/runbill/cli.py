"""runbill command line."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from . import __version__, render
from .core import DEFAULT_RATES, OrgReport, Report, build_org_report, build_report
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
    if isinstance(report, OrgReport):
        s = {"text": lambda: render.org_text(report, top), "md": lambda: render.org_markdown(report, top),
             "json": lambda: render.as_json(report), "csv": lambda: render.org_csv(report)}[fmt]()
    else:
        s = {"text": lambda: render.text(report, top), "md": lambda: render.markdown(report, top),
             "json": lambda: render.as_json(report), "csv": lambda: render.as_csv(report)}[fmt]()
    if out:
        with open(out, "a" if out == os.environ.get("GITHUB_STEP_SUMMARY") else "w", encoding="utf-8") as f:
            f.write(s if s.endswith("\n") else s + "\n")
    else:
        print(s)


def _since(a) -> str:
    return a.since or (datetime.now(timezone.utc) - timedelta(days=a.days)).strftime("%Y-%m-%d")


def _add_common(p: argparse.ArgumentParser, *, max_runs_default: int = 500) -> None:
    p.add_argument("--days", type=int, default=30, help="look back N days (default 30)")
    p.add_argument("--since", help="start date YYYY-MM-DD (overrides --days)")
    p.add_argument("--max-runs", type=int, default=max_runs_default,
                   help=f"stop after N runs per repo (default {max_runs_default})")
    p.add_argument("--top", type=int, default=10, help="rows per table (default 10)")
    p.add_argument("--rate", action="append", metavar="SKU=USD", help="override $/min, e.g. macos=0.08")
    p.add_argument("--format", choices=["text", "md", "json", "csv"], default="text")
    p.add_argument("--output", "-o", help="write to file instead of stdout")
    p.add_argument("--fail-over", type=float, metavar="USD", help="exit 3 if total cost exceeds USD")


def _fetch_repo_report(cli: Client, full_name: str, private: Optional[bool], since: str,
                       max_runs: int, rates: dict) -> Optional[Report]:
    """Fetch runs+jobs for one repo. Returns None if no completed runs (or Actions unavailable)."""
    try:
        runs = list(cli.runs(full_name, since, max_runs + 1))
    except GitHubError as e:
        msg = str(e)
        # Actions disabled / no access → skip quietly
        if "HTTP 404" in msg or "HTTP 409" in msg:
            return None
        raise
    if not runs:
        return None
    truncated = len(runs) > max_runs
    runs = runs[:max_runs]
    with ThreadPoolExecutor(max_workers=8) as ex:
        jobs = dict(zip([x["id"] for x in runs], ex.map(lambda x: cli.jobs(full_name, x["id"]), runs)))
    return build_report(full_name, since, runs, jobs, rates, private=private, truncated=truncated)


def _cmd_report(a) -> int:
    repo = a.repo or _detect_repo()
    if not repo or "/" not in repo:
        print("runbill: give OWNER/REPO (could not detect it from git origin)", file=sys.stderr)
        return 2
    since = _since(a)
    rates = _rates(a.rate)
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
    rep = build_report(repo, since, runs, jobs, rates, private=meta.get("private"), truncated=truncated)
    _emit(rep, a.format, a.top, a.output)
    if a.fail_over is not None and rep.total.cost > a.fail_over:
        print(f"runbill: total ${rep.total.cost:.2f} is over --fail-over ${a.fail_over:.2f}", file=sys.stderr)
        return 3
    return 0


def _cmd_org(a) -> int:
    owner = a.org
    if not owner or "/" in owner:
        print("runbill: give an ORG or USER login (not OWNER/REPO); use `runbill report` for one repo",
              file=sys.stderr)
        return 2
    since = _since(a)
    rates = _rates(a.rate)
    cli = Client(find_token())
    try:
        repos = cli.list_repos(owner, include_archived=a.include_archived)
    except GitHubError as e:
        print(f"runbill: {e}", file=sys.stderr)
        return 1
    if not repos:
        print(f"runbill: no repos found for {owner}", file=sys.stderr)
        return 1
    print(f"runbill: scanning {len(repos)} repos for {owner} since {since}…", file=sys.stderr)
    reports: List[Report] = []
    errors: List[str] = []
    # Up to 4 repos in parallel; each repo fans out its own job fetches (see _fetch_repo_report).
    # Org scans burn the rate limit fast — narrow --days / --max-runs if you hit 403.
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {
            ex.submit(_fetch_repo_report, cli, r["full_name"], r.get("private"), since, a.max_runs, rates): r
            for r in repos
        }
        done = 0
        for fut in as_completed(futs):
            done += 1
            meta = futs[fut]
            name = meta["full_name"]
            try:
                rep = fut.result()
            except GitHubError as e:
                errors.append(f"{name}: {e}")
                print(f"runbill: skip {name}: {e}", file=sys.stderr)
                continue
            if rep is not None:
                reports.append(rep)
                print(f"runbill: [{done}/{len(repos)}] {name}: "
                      f"{rep.run_count} runs, ${rep.total.cost:.2f}", file=sys.stderr)
            elif done % 10 == 0 or done == len(repos):
                print(f"runbill: [{done}/{len(repos)}] …", file=sys.stderr)
    if not reports and errors and len(errors) == len(repos):
        print("runbill: every repo failed; check token scopes (actions:read) and rate limit", file=sys.stderr)
        return 1
    org_rep = build_org_report(owner, since, reports, repo_scanned=len(repos))
    _emit(org_rep, a.format, a.top, a.output)
    if a.fail_over is not None and org_rep.total.cost > a.fail_over:
        print(f"runbill: total ${org_rep.total.cost:.2f} is over --fail-over ${a.fail_over:.2f}",
              file=sys.stderr)
        return 3
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="runbill", description="Which GitHub Actions workflow and job is eating "
                                "your minutes? Per-workflow/per-job billed minutes and cost from the runs API.")
    p.add_argument("--version", action="version", version=f"runbill {__version__}")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("report", help="report on a repository (default command)")
    r.add_argument("repo", nargs="?", help="OWNER/REPO (default: GITHUB_REPOSITORY or git origin)")
    _add_common(r, max_runs_default=500)
    r.add_argument("--workflow", help="only this workflow (file name like ci.yml, or id)")
    r.add_argument("--branch", help="only runs on this branch")
    o = sub.add_parser("org", help="roll up across all repos of an org/user, ranked by cost")
    o.add_argument("org", help="ORG or USER login")
    _add_common(o, max_runs_default=200)
    o.add_argument("--include-archived", action="store_true",
                   help="include archived repos (skipped by default)")
    d = sub.add_parser("demo", help="offline sample report (no network)")
    d.add_argument("--format", choices=["text", "md", "json", "csv"], default="text")
    sub.add_parser("rates", help="print the default $/min table")

    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ("report", "demo", "rates", "org", "-h", "--help", "--version"):
        argv.insert(0, "report")
    a = p.parse_args(argv)
    if a.cmd is None:
        p.print_help()
        return 0
    if a.cmd == "rates":
        for k, v in DEFAULT_RATES.items():
            print(f"{k:<20} ${v:.3f}/min")
        return 0
    if a.cmd == "demo":
        from .demo import sample
        runs, jobs = sample()
        rep = build_report("example/app", "2026-10-01", runs, jobs, private=True)
        _emit(rep, a.format, 10, None)
        return 0
    if a.cmd == "org":
        return _cmd_org(a)
    return _cmd_report(a)


if __name__ == "__main__":
    sys.exit(main())
