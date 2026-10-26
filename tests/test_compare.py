"""--compare: windows, run splitting, diff math, new/gone rows, formats, gates and the CLI (mocked API)."""
import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from runbill import cli, render
from runbill.compare import (Delta, build_comparison, collapse_deltas, compare_windows, diff_lines,
                             increase_over, split_runs)
from runbill.core import Line, build_org_report, build_report

NOW = datetime(2026, 10, 26, 3, 0, tzinfo=timezone.utc)


def at(days_ago, hours=0):
    return (NOW - timedelta(days=days_ago, hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def job(labels, secs, name="j", attempt=1):
    return {"name": name, "labels": labels, "run_attempt": attempt, "conclusion": "success",
            "started_at": "2026-10-01T00:00:00Z",
            "completed_at": (datetime(2026, 10, 1, tzinfo=timezone.utc) + timedelta(seconds=secs))
            .strftime("%Y-%m-%dT%H:%M:%SZ")}


def run(rid, created, name="CI", event="push", branch="main"):
    return {"id": rid, "name": name, "created_at": created, "event": event, "head_branch": branch,
            "status": "completed", "repository": {"full_name": "o/r"}, "head_repository": {"full_name": "o/r"}}


def line(key, cost, minutes=10, runs=1, jobs=1):
    x = Line(key)
    x.cost, x.billed_minutes, x.runs, x.jobs = cost, minutes, runs, jobs
    return x


# Two weeks of a small repo. Before: CI (linux 10 min x2 = $0.12), Bench ($0.20). Now: CI on macOS too,
# Docs is new, Bench is gone.
RUNS = [  # newest first, like the API
    run(10, at(1), "Docs"),
    run(9, at(2), "CI"),
    run(8, at(3), "CI"),
    run(3, at(8), "Bench"),
    run(2, at(9), "CI"),
    run(1, at(10), "CI"),
]
JOBS = {
    10: [job(["ubuntu-latest"], 30, "build")],                                     # 1 min  $0.006
    9: [job(["ubuntu-latest"], 600, "test"), job(["macos-14"], 300, "mac")],       # 10 + 5 mac
    8: [job(["ubuntu-latest"], 600, "test"), job(["macos-14"], 300, "mac")],
    3: [job(["ubuntu-latest-4-cores"], 1000, "bench")],                            # 17 min x $0.012
    2: [job(["ubuntu-latest"], 600, "test")],
    1: [job(["ubuntu-latest"], 600, "test")],
}


def two_reports(runs=RUNS, jobs=JOBS, max_runs=500):
    prev_w, cur_w = compare_windows(NOW, days=7)
    p, c, pt, ct = split_runs(runs, prev_w, cur_w, max_runs)
    prev = build_report("o/r", "x", p, jobs, private=True, truncated=pt)
    cur = build_report("o/r", "x", c, jobs, private=True, truncated=ct)
    return build_comparison(prev, cur, prev_w, cur_w, days=7)


# --- windows --------------------------------------------------------------------------------------

def test_windows_from_days_are_back_to_back_and_equal():
    prev, cur = compare_windows(NOW, days=7)
    assert cur.end == NOW and cur.start == NOW - timedelta(days=7)
    assert prev.end == cur.start and prev.start == NOW - timedelta(days=14)
    assert prev.days == cur.days == 7


def test_windows_from_since_mirror_the_length():
    prev, cur = compare_windows(NOW, since="2026-10-20")
    assert cur.start == datetime(2026, 10, 20, tzinfo=timezone.utc)
    assert cur.end - cur.start == prev.end - prev.start == timedelta(days=6, hours=3)
    assert prev.end == cur.start


@pytest.mark.parametrize("kw,msg", [({"since": "2026-10-27"}, "not in the past"),
                                    ({"since": "2026-10-26T00"}, "not a date"), ({"days": 0}, "1 or more")])
def test_windows_errors(kw, msg):
    with pytest.raises(ValueError, match=msg):
        compare_windows(NOW, **kw)


# --- splitting one fetch --------------------------------------------------------------------------

def test_split_by_created_at_drops_older_and_keeps_undated_in_current():
    prev_w, cur_w = compare_windows(NOW, days=7)
    runs = [run(5, None), run(4, at(0, 1)), run(3, at(7)), run(2, at(7, 1)), run(1, at(14, 2))]
    p, c, pt, ct = split_runs(runs, prev_w, cur_w, 100)
    assert [r["id"] for r in c] == [5, 4, 3]   # exactly 7 days ago belongs to the current window
    assert [r["id"] for r in p] == [2]          # run 1 is older than the previous window
    assert (pt, ct) == (False, False)


def test_split_flags_previous_truncated_when_cap_hit_inside_it():
    prev_w, cur_w = compare_windows(NOW, days=7)
    runs = [run(i, at(1)) for i in range(3)] + [run(10 + i, at(8)) for i in range(5)]  # 8 runs, cap 2*3
    p, c, pt, ct = split_runs(runs, prev_w, cur_w, 3)
    assert len(c) == 3 and len(p) == 3 and pt and not ct


def test_split_not_truncated_when_fetch_reached_older_runs():
    prev_w, cur_w = compare_windows(NOW, days=7)
    runs = [run(1, at(1)), run(2, at(8)), run(3, at(20)), run(4, at(21)), run(5, at(22))]
    p, c, pt, ct = split_runs(runs, prev_w, cur_w, 2)  # cap 4, hit, but an older run was seen
    assert (len(p), len(c), pt, ct) == (1, 1, False, False)


def test_split_current_over_cap():
    prev_w, cur_w = compare_windows(NOW, days=7)
    runs = [run(i, at(1)) for i in range(7)]
    p, c, pt, ct = split_runs(runs, prev_w, cur_w, 3)
    assert len(c) == 3 and ct and p == [] and pt


# --- diff math ------------------------------------------------------------------------------------

def test_delta_math_and_status():
    d = Delta("x", line("x", 2.0, 20), line("x", 3.0, 25), True, True)
    assert d.cost_delta == pytest.approx(1.0) and d.minutes_delta == 5
    assert d.cost_pct == pytest.approx(50.0) and d.status == "up"
    assert Delta("x", line("x", 2.0), line("x", 1.0), True, True).status == "down"
    assert Delta("x", line("x", 2.0), line("x", 2.001), True, True).status == "flat"


def test_zero_cost_previous_has_no_percentage():
    free_before = Delta("x", line("x", 0.0), line("x", 1.0), True, True)  # e.g. moved off self-hosted
    assert free_before.cost_pct is None and free_before.status == "up"
    assert render._pct_cell(free_before) == "from $0"
    free_both = Delta("x", line("x", 0.0), line("x", 0.0), True, True)
    assert free_both.cost_pct is None and render._pct_cell(free_both) == "–"
    assert free_both.as_dict()["delta"]["cost_pct"] is None


def test_diff_lines_pairs_marks_new_gone_and_ranks_by_increase():
    prev = [line("a", 1.0), line("b", 5.0), line("gone", 0.5)]
    cur = [line("a", 4.0), line("b", 4.0), line("new", 2.0)]
    rows = diff_lines(prev, cur)
    assert [d.key for d in rows] == ["a", "new", "gone", "b"]
    s = {d.key: d for d in rows}
    assert s["new"].status == "new" and s["new"].cost_pct is None and render._pct_cell(s["new"]) == "new"
    assert s["gone"].status == "gone" and s["gone"].cost_delta == pytest.approx(-0.5)
    assert render._pct_cell(s["gone"]) == "gone"
    assert s["a"].cost_pct == pytest.approx(300.0)


def test_comparison_numbers_and_sections_add_up():
    c = two_reports()
    assert c.previous.run_count == 3 and c.current.run_count == 3
    wf = {d.key: d for d in c.sections["workflows"]}
    assert wf["CI"].previous.billed_minutes == 20 and wf["CI"].current.billed_minutes == 30
    assert wf["CI"].previous.cost == pytest.approx(0.12)
    assert wf["CI"].current.cost == pytest.approx(0.12 + 10 * 0.062)
    assert wf["Docs"].status == "new" and wf["Bench"].status == "gone"
    assert wf["Bench"].previous.cost == pytest.approx(17 * 0.012)
    assert c.sections["workflows"][0].key == "CI"  # biggest increase first
    assert {d.key: d.status for d in c.sections["jobs"]}["CI › mac"] == "new"
    for key in ("workflows", "jobs", "branches", "events"):
        assert sum(d.cost_delta for d in c.sections[key]) == pytest.approx(c.total.cost_delta), key
        assert sum(d.minutes_delta for d in c.sections[key]) == pytest.approx(c.total.minutes_delta), key


def test_collapse_deltas_sums_and_names_folded_new_and_gone():
    rows = diff_lines([line("a", 1), line("b", 1), line("g", 1)], [line("a", 3), line("b", 2), line("n", 1),
                                                                   line("m", 0.5)])
    shown, other = collapse_deltas(rows, 2, "workflows")
    assert [d.key for d in shown] == ["a", "b"]  # b and n both +$1: the bigger one now wins the tie
    assert other.key == "3 other workflows (2 new, 1 gone)"
    assert sum(d.cost_delta for d in shown) + other.cost_delta == pytest.approx(sum(d.cost_delta for d in rows))
    assert collapse_deltas(rows[:3], 2, "workflows")[1] is None  # one leftover is shown, not folded


def test_increase_gate():
    c = two_reports()
    over, pct = increase_over(c, 10)
    assert over and pct == pytest.approx(c.total.cost_pct)
    assert increase_over(c, 10_000) == (False, pytest.approx(pct))
    empty = build_report("o/r", "x", [], {})
    zero = build_comparison(empty, c.current, c.previous_window, c.current_window)
    assert increase_over(zero, 0) == (False, None)


def test_org_comparison_by_repo():
    a_prev = build_report("o/a", "x", [run(1, at(9))], {1: [job(["ubuntu-latest"], 600)]})
    a_cur = build_report("o/a", "x", [run(2, at(1))], {2: [job(["macos-14"], 600)]})
    b_prev = build_report("o/b", "x", [run(3, at(9))], {3: [job(["ubuntu-latest"], 60)]})
    c_cur = build_report("o/c", "x", [run(4, at(1))], {4: [job(["ubuntu-latest"], 60)]})
    prev_w, cur_w = compare_windows(NOW, days=7)
    c = build_comparison(build_org_report("o", "x", [a_prev, b_prev], 3), build_org_report("o", "x", [a_cur, c_cur], 3),
                         prev_w, cur_w, days=7)
    assert c.is_org
    st = {d.key: d.status for d in c.sections["repos"]}
    assert st == {"o/a": "up", "o/b": "gone", "o/c": "new"}
    assert c.sections["repos"][0].key == "o/a"
    t = render.compare_text(c)
    assert "org o · last 7 days vs the 7 days before" in t and "BY REPO" in t and "BY JOB" not in t
    d = json.loads(render.compare_json(c))
    assert d["org"] == "o" and [r["name"] for r in d["repos"]][0] == "o/a" and "workflows" not in d


# --- formats --------------------------------------------------------------------------------------

def test_text_output():
    t = render.compare_text(two_reports())
    assert t.splitlines()[0] == "runbill · o/r · last 7 days vs the 7 days before"
    assert "  now     2026-10-19 03:00 → 2026-10-26 03:00 UTC" in t
    assert "  before  2026-10-12 03:00 → 2026-10-19 03:00 UTC" in t
    assert "Biggest increase: CI +$0.62 (+516.7%), led by mac +$0.62 (new)." in t
    rows = {ln.split()[0]: ln for ln in t.splitlines() if ln.startswith("  ") and ln.split()}
    assert rows["Docs"].rstrip().endswith("new") and rows["Bench"].rstrip().endswith("gone")
    assert "BY WORKFLOW" in t and "BY JOB" in t and "BY BRANCH" not in t


def test_text_columns_line_up():
    t = render.compare_text(two_reports(), by=["branch"])
    lines = t.splitlines()
    head = next(ln for ln in lines if ln.lstrip().startswith("BY WORKFLOW"))
    ci = next(ln for ln in lines if ln.lstrip().startswith("CI "))
    for col in ("min now", "cost now", "Δ cost", "Δ %"):
        end = head.index(col) + len(col)
        assert ci[end - 1] != " " and (end == len(ci) or ci[end] == " "), col
    widths = {len(ln) for ln in lines if ln.lstrip().startswith("BY ")}
    assert len(widths) == 1  # every table has the same width


def test_text_no_increase_and_empty():
    c = two_reports()
    same = build_comparison(c.current, c.current, c.previous_window, c.current_window, days=7)
    t = render.compare_text(same)
    assert "No workflow got more expensive." in t and "TOTAL   $0.75 → $0.75   $0.00   billed" in t
    empty = build_report("o/r", "x", [], {})
    t = render.compare_text(build_comparison(empty, empty, c.previous_window, c.current_window, days=7))
    assert "(no runs in either window)" in t and "$0.00 → $0.00   $0.00   billed" in t


def test_since_header_and_truncation_warning():
    prev_w, cur_w = compare_windows(NOW, since="2026-10-20")
    runs = [run(i, at(1)) for i in range(2)] + [run(10 + i, at(9)) for i in range(5)]
    p, c, pt, ct = split_runs(runs, prev_w, cur_w, 2)
    jobs = {r["id"]: [job(["ubuntu-latest"], 60)] for r in runs}
    cmp = build_comparison(build_report("o/r", "x", p, jobs, truncated=pt),
                           build_report("o/r", "x", c, jobs, truncated=ct), prev_w, cur_w)
    t = render.compare_text(cmp)
    assert "since 2026-10-20 vs the 6.1 days before" in t
    assert "previous window hit --max-runs" in t and "overstated" in t
    assert "Previous window hit --max-runs" in render.compare_markdown(cmp)


def test_markdown_output():
    md = render.compare_markdown(two_reports(), by=["event"])
    assert md.startswith("### runbill · `o/r` · last 7 days vs the 7 days before")
    assert "| Workflow | Billed min before | Billed min now | Cost before | Cost now | Δ cost | Δ % |" in md
    assert "| Docs | – | 1 | – | $0.01 | **+$0.01** | **new** |" in md
    assert "| Bench | 17 | – | $0.20 | – | -$0.20 | **gone** |" in md
    assert "| `push` |" in md and "| Event |" in md


def test_json_has_both_periods_and_deltas():
    d = json.loads(render.compare_json(two_reports(), by=["branch", "event"]))
    assert d["repo"] == "o/r"
    assert d["compare"]["previous"]["from"] == "2026-10-12T03:00:00Z"
    assert d["compare"]["current"]["to"] == "2026-10-26T03:00:00Z"
    assert d["compare"]["current"]["runs"] == 3 and d["compare"]["current"]["days"] == 7
    assert d["compare"]["previous"]["total"]["billed_minutes"] == 37
    wf = {x["name"]: x for x in d["workflows"]}
    assert wf["Docs"]["status"] == "new" and wf["Docs"]["delta"]["cost_pct"] is None
    assert wf["Bench"]["status"] == "gone" and wf["Bench"]["current"]["cost_usd"] == 0
    assert wf["CI"]["delta"]["cost_pct"] == pytest.approx(516.67)
    assert set(wf["CI"]) == {"name", "status", "previous", "current", "delta"}
    assert "branches" in d and "events" in d and "jobs" in d
    assert "branches" not in json.loads(render.compare_json(two_reports()))


def test_csv_rows():
    rows = list(csv.DictReader(io.StringIO(render.compare_csv(two_reports(), by=["event"]))))
    assert rows[0]["level"] == "total"
    assert {r["level"] for r in rows} == {"total", "workflow", "job", "event"}
    docs = next(r for r in rows if r["name"] == "Docs")
    assert docs["status"] == "new" and docs["delta_cost_pct"] == "" and docs["runs_before"] == "0"


# --- CLI ------------------------------------------------------------------------------------------

def test_demo_compare_all_formats(capsys):
    for fmt in ("text", "md", "json", "csv"):
        assert cli.main(["demo", "--compare", "--format", fmt, "--by", "branch,event"]) == 0
    out = capsys.readouterr().out
    assert "Biggest increase: CI" in out and "Benchmarks" in out and "test (macos)" in out


def test_demo_compare_reconciles_with_plain_demo(capsys):
    cli.main(["demo", "--compare", "--format", "json"])
    d = json.loads(capsys.readouterr().out)
    cli.main(["demo", "--format", "json"])
    plain = json.loads(capsys.readouterr().out)
    assert d["compare"]["current"]["total"] == plain["total"]  # the current week is the plain demo
    st = {w["name"]: w["status"] for w in d["workflows"]}
    assert st == {"CI": "up", "E2E nightly": "up", "Release": "new", "Docs": "down", "Benchmarks": "gone"}


class FakeClient:
    calls = []

    def __init__(self, token=None):
        pass

    def repo(self, repo):
        return {"private": True}

    def runs(self, repo, since, max_runs, workflow=None, branch=None):
        FakeClient.calls.append(("runs", repo, since, max_runs))
        return iter(RUNS[:max_runs])

    def jobs(self, repo, run_id):
        FakeClient.calls.append(("jobs", repo, run_id))
        return JOBS[run_id]

    def list_repos(self, owner, include_archived=False):
        return [{"full_name": "o/r", "private": True}, {"full_name": "o/quiet", "private": True}]


@pytest.fixture
def fake(monkeypatch):
    FakeClient.calls = []
    monkeypatch.setattr(cli, "Client", FakeClient)
    monkeypatch.setattr(cli, "find_token", lambda: "t")
    monkeypatch.setattr(cli, "_now", lambda: NOW)
    return FakeClient


def test_cli_report_compare_fetches_once(fake, capsys):
    assert cli.main(["o/r", "--compare", "--days", "7", "--max-runs", "50"]) == 0
    runs_calls = [c for c in fake.calls if c[0] == "runs"]
    assert runs_calls == [("runs", "o/r", "2026-10-12", 101)]  # one fetch from the previous window's date
    assert sorted(c[2] for c in fake.calls if c[0] == "jobs") == [1, 2, 3, 8, 9, 10]
    out = capsys.readouterr().out
    assert "o/r · last 7 days vs the 7 days before" in out


def test_cli_fail_increase(fake, capsys):
    assert cli.main(["o/r", "--compare", "--days", "7", "--fail-increase", "50%"]) == 3
    assert "over --fail-increase 50%" in capsys.readouterr().err
    assert cli.main(["o/r", "--compare", "--days", "7", "--fail-increase", "1000"]) == 0
    assert cli.main(["o/r", "--compare", "--days", "7", "--fail-over", "0.5"]) == 3
    assert "over --fail-over $0.50" in capsys.readouterr().err


def test_cli_fail_increase_with_free_previous_window(fake, monkeypatch, capsys):
    monkeypatch.setattr(FakeClient, "runs", lambda self, *a, **k: iter(RUNS[:3]))
    assert cli.main(["o/r", "--compare", "--days", "7", "--fail-increase", "0"]) == 0
    assert "previous window cost $0.00" in capsys.readouterr().err


def test_cli_compare_flag_errors(fake, capsys):
    assert cli.main(["o/r", "--fail-increase", "20"]) == 2
    assert "--fail-increase needs --compare" in capsys.readouterr().err
    assert cli.main(["o/r", "--compare", "--since", "2027-01-01"]) == 2
    assert "not in the past" in capsys.readouterr().err
    with pytest.raises(SystemExit) as e:
        cli.main(["o/r", "--compare", "--fail-increase", "lots"])
    assert e.value.code == 2
    assert "not a percentage" in capsys.readouterr().err


def test_cli_org_compare(fake, monkeypatch, capsys):
    def runs(self, repo, since, max_runs, workflow=None, branch=None):
        return iter(RUNS if repo == "o/r" else [])
    monkeypatch.setattr(FakeClient, "runs", runs)
    assert cli.main(["org", "o", "--compare", "--days", "7", "--format", "json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["org"] == "o" and [r["name"] for r in d["repos"]] == ["o/r"]
    assert d["compare"]["previous"]["runs"] == 3 and d["compare"]["current"]["runs"] == 3


def test_cli_help_mentions_compare(capsys):
    with pytest.raises(SystemExit):
        cli.main(["report", "--help"])
    out = capsys.readouterr().out
    assert "--compare" in out and "--fail-increase" in out
