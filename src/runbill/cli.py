"""runbill command line."""
from __future__ import annotations

import argparse
import difflib
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from . import __version__, render
from .compare import Comparison, Window, build_comparison, compare_windows, increase_over, split_runs
from .core import DEFAULT_RATES, GROUPINGS, OrgReport, Report, build_org_report, build_report
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


_BY_ALIASES = {"branches": "branch", "events": "event", "trigger": "event", "triggers": "event"}


def _by_arg(value: str) -> List[str]:
    """Parse one --by value: `branch`, `event` or a list like `branch,event` (commas or spaces)."""
    out = []
    for part in re.split(r"[,\s]+", value):
        part = part.strip().lower()
        if not part:
            continue
        part = _BY_ALIASES.get(part, part)
        if part not in GROUPINGS:
            close = difflib.get_close_matches(part, GROUPINGS, n=1)
            hint = f" (did you mean {close[0]!r}?)" if close else ""
            raise argparse.ArgumentTypeError(
                f"{part!r} is not a breakdown{hint}; use branch, event, or branch,event")
        out.append(part)
    return out


def _top_arg(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a whole number") from None
    if n < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return n


def _by(a) -> List[str]:
    """Flatten repeated --by values, keeping the order given and dropping repeats."""
    seen: List[str] = []
    for chunk in getattr(a, "by", None) or []:
        for g in chunk:
            if g not in seen:
                seen.append(g)
    return seen


def _emit(report, fmt, top, out, by=()):
    if isinstance(report, Comparison):
        s = {"text": lambda: render.compare_text(report, top, by),
             "md": lambda: render.compare_markdown(report, top, by),
             "json": lambda: render.compare_json(report, by), "csv": lambda: render.compare_csv(report, by)}[fmt]()
    elif isinstance(report, OrgReport):
        s = {"text": lambda: render.org_text(report, top, by),
             "md": lambda: render.org_markdown(report, top, by),
             "json": lambda: render.as_json(report, by), "csv": lambda: render.org_csv(report, by)}[fmt]()
    else:
        s = {"text": lambda: render.text(report, top, by), "md": lambda: render.markdown(report, top, by),
             "json": lambda: render.as_json(report, by), "csv": lambda: render.as_csv(report, by)}[fmt]()
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
    p.add_argument("--top", type=_top_arg, default=10,
                   help="rows per table (default 10); with --by, the remaining branches/events are "
                        "summed into one 'N other' row")
    p.add_argument("--rate", action="append", metavar="SKU=USD", help="override $/min, e.g. macos=0.08")
    _add_by(p)
    p.add_argument("--format", choices=["text", "md", "json", "csv"], default="text")
    p.add_argument("--output", "-o", help="write to file instead of stdout")
    p.add_argument("--fail-over", type=float, metavar="USD", help="exit 3 if total cost exceeds USD")
    _add_compare(p)
    p.add_argument("--fail-increase", type=_pct_arg, metavar="PCT",
                   help="with --compare: exit 3 if total cost rose more than PCT%% over the previous window")


def _pct_arg(value: str) -> float:
    try:
        n = float(value.strip().rstrip("%"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a percentage like 25") from None
    if n < 0:
        raise argparse.ArgumentTypeError("must be 0 or more (it is the allowed increase)")
    return n


def _add_compare(p: argparse.ArgumentParser) -> None:
    p.add_argument("--compare", action="store_true",
                   help="compare with the window just before, of the same length (e.g. --days 7: the last "
                        "7 days vs the 7 before): per-workflow and per-job change, biggest increase first")


def _add_by(p: argparse.ArgumentParser) -> None:
    p.add_argument("--by", type=_by_arg, action="append", metavar="branch|event",
                   help="also break minutes and cost down by branch and/or trigger event "
                        "(push, pull_request, schedule, ...); e.g. --by branch,event")


def _fetch_repo_report(cli: Client, full_name: str, private: Optional[bool], since: str,
                       max_runs: int, rates: dict,
                       windows: "tuple[Window, Window] | None" = None):
    """Fetch runs+jobs for one repo. Returns None if no completed runs (or Actions unavailable).

    With `windows` (previous, current) it fetches once from the previous window's start and returns a
    (previous, current) pair of Reports instead.
    """
    if windows is not None:
        since, fetch_cap = windows[0].start.strftime("%Y-%m-%d"), 2 * max_runs + 1
    else:
        fetch_cap = max_runs + 1
    try:
        runs = list(cli.runs(full_name, since, fetch_cap))
    except GitHubError as e:
        msg = str(e)
        # Actions disabled / no access → skip quietly
        if "HTTP 404" in msg or "HTTP 409" in msg:
            return None
        raise
    if windows is not None:
        keep = _in_windows(runs, windows[0], windows[1], max_runs)
        if not keep:
            return None
        with ThreadPoolExecutor(max_workers=8) as ex:
            jobs = dict(zip([x["id"] for x in keep], ex.map(lambda x: cli.jobs(full_name, x["id"]), keep)))
        return _split_reports(full_name, runs, jobs, windows[0], windows[1], max_runs, rates, private)
    if not runs:
        return None
    truncated = len(runs) > max_runs
    runs = runs[:max_runs]
    with ThreadPoolExecutor(max_workers=8) as ex:
        jobs = dict(zip([x["id"] for x in runs], ex.map(lambda x: cli.jobs(full_name, x["id"]), runs)))
    return build_report(full_name, since, runs, jobs, rates, private=private, truncated=truncated)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)


def _windows(a) -> "tuple[Window, Window] | None":
    """(previous, current) for --compare, or None (after printing why) if the options don't allow it."""
    try:
        return compare_windows(_now(), a.days, a.since)
    except ValueError as e:
        print(f"runbill: {e}", file=sys.stderr)
        return None


def _check_compare_flags(a) -> bool:
    if getattr(a, "fail_increase", None) is not None and not a.compare:
        print("runbill: --fail-increase needs --compare (it checks the change against the previous window)",
              file=sys.stderr)
        return False
    return True


def _gates(total_cost: float, a, cmp: "Comparison | None" = None) -> int:
    """Budget gates after the report is written: --fail-over, then --fail-increase. Exit 3 if either trips."""
    code = 0
    if a.fail_over is not None and total_cost > a.fail_over:
        print(f"runbill: total ${total_cost:.2f} is over --fail-over ${a.fail_over:.2f}", file=sys.stderr)
        code = 3
    if cmp is not None and getattr(a, "fail_increase", None) is not None:
        over, pct = increase_over(cmp, a.fail_increase)
        before, now = cmp.previous.total.cost, cmp.current.total.cost
        if pct is None:
            print(f"runbill: previous window cost $0.00, so there is no percentage to check against "
                  f"--fail-increase {a.fail_increase:g}% (now ${now:.2f})", file=sys.stderr)
        elif over:
            print(f"runbill: total cost up {pct:.1f}% (${before:.2f} → ${now:.2f}), over --fail-increase "
                  f"{a.fail_increase:g}%", file=sys.stderr)
            code = 3
    return code


def _split_reports(name: str, runs: List[dict], jobs: dict, prev_w: Window, cur_w: Window, max_runs: int,
                   rates: dict, private: Optional[bool]) -> "tuple[Report, Report]":
    prev_runs, cur_runs, prev_trunc, cur_trunc = split_runs(runs, prev_w, cur_w, max_runs)
    label = "%Y-%m-%d %H:%M"
    prev = build_report(name, prev_w.start.strftime(label), prev_runs, jobs, rates, private=private,
                        truncated=prev_trunc)
    cur = build_report(name, cur_w.start.strftime(label), cur_runs, jobs, rates, private=private,
                       truncated=cur_trunc)
    return prev, cur


def _in_windows(runs: List[dict], prev_w: Window, cur_w: Window, max_runs: int) -> List[dict]:
    """The runs split_runs will keep, so jobs are fetched only for those."""
    p, c, _, _ = split_runs(runs, prev_w, cur_w, max_runs)
    return c + p


def _cmd_report(a) -> int:
    repo = a.repo or _detect_repo()
    if not repo or "/" not in repo:
        print("runbill: give OWNER/REPO (could not detect it from git origin)", file=sys.stderr)
        return 2
    if not _check_compare_flags(a):
        return 2
    if a.compare:
        return _cmd_report_compare(a, repo)
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
    _emit(rep, a.format, a.top, a.output, _by(a))
    return _gates(rep.total.cost, a)


def _cmd_report_compare(a, repo: str) -> int:
    windows = _windows(a)
    if windows is None:
        return 2
    prev_w, cur_w = windows
    rates = _rates(a.rate)
    cli = Client(find_token())
    try:
        meta = cli.repo(repo)
        # One fetch from the start of the previous window (its date; the API filters by day), newest first,
        # capped at --max-runs per window; split_runs files each run by created_at.
        runs = list(cli.runs(repo, prev_w.start.strftime("%Y-%m-%d"), 2 * a.max_runs + 1, a.workflow, a.branch))
        keep = _in_windows(runs, prev_w, cur_w, a.max_runs)
        print(f"runbill: fetching jobs for {len(keep)} runs across both windows…", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=8) as ex:
            jobs = dict(zip([x["id"] for x in keep], ex.map(lambda x: cli.jobs(repo, x["id"]), keep)))
    except GitHubError as e:
        print(f"runbill: {e}", file=sys.stderr)
        return 1
    prev, cur = _split_reports(repo, runs, jobs, prev_w, cur_w, a.max_runs, rates, meta.get("private"))
    cmp = build_comparison(prev, cur, prev_w, cur_w, days=None if a.since else a.days)
    _emit(cmp, a.format, a.top, a.output, _by(a))
    return _gates(cur.total.cost, a, cmp)


def _cmd_org(a) -> int:
    owner = a.org
    if not owner or "/" in owner:
        print("runbill: give an ORG or USER login (not OWNER/REPO); use `runbill report` for one repo",
              file=sys.stderr)
        return 2
    if not _check_compare_flags(a):
        return 2
    windows = None
    if a.compare:
        windows = _windows(a)
        if windows is None:
            return 2
    since = _since(a) if windows is None else windows[0].start.strftime("%Y-%m-%d")
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
    span = f"since {since}" if windows is None else f"from {since} (both windows)"
    print(f"runbill: scanning {len(repos)} repos for {owner} {span}…", file=sys.stderr)
    reports: list = []
    errors: List[str] = []
    # Up to 4 repos in parallel; each repo fans out its own job fetches (see _fetch_repo_report).
    # Org scans burn the rate limit fast — narrow --days / --max-runs if you hit 403.
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {
            ex.submit(_fetch_repo_report, cli, r["full_name"], r.get("private"), since, a.max_runs, rates,
                      windows): r
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
                if isinstance(rep, tuple):
                    print(f"runbill: [{done}/{len(repos)}] {name}: ${rep[0].total.cost:.2f} → "
                          f"${rep[1].total.cost:.2f}", file=sys.stderr)
                else:
                    print(f"runbill: [{done}/{len(repos)}] {name}: "
                          f"{rep.run_count} runs, ${rep.total.cost:.2f}", file=sys.stderr)
            elif done % 10 == 0 or done == len(repos):
                print(f"runbill: [{done}/{len(repos)}] …", file=sys.stderr)
    if not reports and errors and len(errors) == len(repos):
        print("runbill: every repo failed; check token scopes (actions:read) and rate limit", file=sys.stderr)
        return 1
    if windows is not None:
        prev_w, cur_w = windows
        # A repo only counts as active in a window where it actually ran.
        prev_org = build_org_report(owner, prev_w.start.strftime("%Y-%m-%d %H:%M"),
                                    [p for p, _ in reports if p.run_count], repo_scanned=len(repos))
        cur_org = build_org_report(owner, cur_w.start.strftime("%Y-%m-%d %H:%M"),
                                   [c for _, c in reports if c.run_count], repo_scanned=len(repos))
        cmp = build_comparison(prev_org, cur_org, prev_w, cur_w, days=None if a.since else a.days)
        _emit(cmp, a.format, a.top, a.output, _by(a))
        return _gates(cur_org.total.cost, a, cmp)
    org_rep = build_org_report(owner, since, reports, repo_scanned=len(repos))
    _emit(org_rep, a.format, a.top, a.output, _by(a))
    return _gates(org_rep.total.cost, a)


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
    d.add_argument("--top", type=_top_arg, default=10, help="rows per table (default 10)")
    _add_by(d)
    _add_compare(d)
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
        from .demo import sample, sample_two_weeks
        if a.compare:
            runs, jobs, now = sample_two_weeks()
            prev_w, cur_w = compare_windows(now, days=7)
            prev, cur = _split_reports("example/app", runs, jobs, prev_w, cur_w, 500, {}, True)
            _emit(build_comparison(prev, cur, prev_w, cur_w, days=7), a.format, a.top, None, _by(a))
            return 0
        runs, jobs = sample()
        rep = build_report("example/app", "2026-10-01", runs, jobs, private=True)
        _emit(rep, a.format, a.top, None, _by(a))
        return 0
    if a.cmd == "org":
        return _cmd_org(a)
    return _cmd_report(a)


if __name__ == "__main__":
    sys.exit(main())
