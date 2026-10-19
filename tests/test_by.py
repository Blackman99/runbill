"""--by branch / --by event: grouping, totals reconciliation, folding, formats, edge cases."""
import csv
import io
import json

import pytest

from runbill import render
from runbill.cli import main
from runbill.core import (NO_BRANCH, UNKNOWN_EVENT, Line, branch_key, build_org_report, build_report,
                          collapse, event_key)
from runbill.demo import sample


def job(labels, secs, attempt=1, conclusion="success", name="j"):
    m, s = divmod(secs, 60)
    return {"name": name, "labels": labels, "run_attempt": attempt, "conclusion": conclusion,
            "started_at": "2026-10-01T00:00:00Z", "completed_at": f"2026-10-01T{m // 60:02d}:{m % 60:02d}:{s:02d}Z"}


def run(rid, branch="main", event="push", name="CI", head="o/r", base="o/r"):
    r = {"id": rid, "name": name, "event": event, "head_branch": branch}
    if head is not None:
        r["head_repository"] = {"full_name": head}
    if base is not None:
        r["repository"] = {"full_name": base}
    return r


def _sum(lines, attr):
    return sum(getattr(x, attr) for x in lines)


def _assert_reconciles(rep):
    t = rep.total
    for lines in (rep.workflows, rep.branches, rep.events):
        assert _sum(lines, "billed_minutes") == t.billed_minutes
        assert _sum(lines, "cost") == pytest.approx(t.cost)
        assert _sum(lines, "rerun_cost") == pytest.approx(t.rerun_cost)
        assert _sum(lines, "jobs") == t.jobs
        assert _sum(lines, "runs") == t.runs


# --- keys ---------------------------------------------------------------------------------------

def test_branch_key_plain_fork_and_missing():
    assert branch_key(run(1, "feat/x")) == "feat/x"
    assert branch_key(run(1, "main", head="someone/r")) == "someone:main"  # fork PR from its own main
    assert branch_key(run(1, "main", head="O/R", base="o/r")) == "main"   # case-insensitive same repo
    assert branch_key(run(1, "fix", head="OctoCat/r")) == "OctoCat:fix"  # owner keeps its case
    assert branch_key(run(1, "main", head=None)) == "main"                # no head repo info
    assert branch_key({"id": 1}) == NO_BRANCH
    assert branch_key({"id": 1, "head_branch": None}) == NO_BRANCH
    assert branch_key({"id": 1, "head_branch": ""}) == NO_BRANCH


def test_event_key_passes_unknown_events_through():
    assert event_key({"event": "pull_request"}) == "pull_request"
    assert event_key({"event": "merge_group"}) == "merge_group"
    assert event_key({"event": "some_future_event"}) == "some_future_event"
    assert event_key({}) == UNKNOWN_EVENT
    assert event_key({"event": None}) == UNKNOWN_EVENT


# --- grouping + billing semantics -----------------------------------------------------------------

def test_groups_use_per_job_round_up_and_reconcile():
    runs = [run(1, "main", "push"), run(2, "feat/a", "pull_request"), run(3, "feat/a", "pull_request"),
            run(4, "main", "schedule", name="Nightly")]
    jobs = {
        1: [job(["ubuntu-latest"], 61), job(["ubuntu-latest"], 1)],        # 2 + 1 = 3 min
        2: [job(["macos-latest"], 30)],                                    # 1 min macOS
        3: [job(["macos-latest"], 90), job(["macos-latest"], 30, attempt=2),
            job(["ubuntu-latest"], 500, conclusion="skipped")],            # 2 + 1, skipped ignored
        4: [job(["ubuntu-latest-8-cores"], 599)],                          # 10 min larger runner
    }
    rep = build_report("o/r", "2026-10-01", runs, jobs)
    b = {x.key: x for x in rep.branches}
    e = {x.key: x for x in rep.events}
    assert b["main"].billed_minutes == 13 and b["main"].runs == 2
    assert b["feat/a"].billed_minutes == 4 and b["feat/a"].runs == 2 and b["feat/a"].jobs == 3
    assert b["feat/a"].cost == pytest.approx(4 * 0.062)
    assert b["feat/a"].rerun_cost == pytest.approx(0.062)
    assert e["push"].billed_minutes == 3
    assert e["pull_request"].billed_minutes == 4
    assert e["schedule"].cost == pytest.approx(10 * 0.022)
    assert e["schedule"].by_sku == {"linux-8-core": 10}
    _assert_reconciles(rep)


def test_ranked_by_cost_not_minutes():
    runs = [run(1, "linux-heavy"), run(2, "mac-light", "pull_request")]
    jobs = {1: [job(["ubuntu-latest"], 600)], 2: [job(["macos-latest"], 120)]}  # $0.06 vs $0.124
    rep = build_report("o/r", "x", runs, jobs)
    assert [x.key for x in rep.branches] == ["mac-light", "linux-heavy"]
    assert [x.key for x in rep.events] == ["pull_request", "push"]


def test_run_without_billed_jobs_still_counts_as_a_run():
    runs = [run(1, "main"), run(2, "docs", "pull_request")]
    jobs = {1: [job(["ubuntu-latest"], 60)], 2: [job(["ubuntu-latest"], 60, conclusion="skipped")]}
    rep = build_report("o/r", "x", runs, jobs)
    docs = next(x for x in rep.branches if x.key == "docs")
    assert docs.runs == 1 and docs.jobs == 0 and docs.cost == 0
    _assert_reconciles(rep)


def test_missing_branch_and_event_are_grouped_not_dropped():
    runs = [{"id": 1, "name": "CI"}, {"id": 2, "name": "CI", "event": "dynamic", "head_branch": None}]
    jobs = {1: [job(["ubuntu-latest"], 60)], 2: [job(["ubuntu-latest"], 120)]}
    rep = build_report("o/r", "x", runs, jobs)
    assert [x.key for x in rep.branches] == [NO_BRANCH]
    assert rep.branches[0].billed_minutes == 3
    assert {x.key for x in rep.events} == {UNKNOWN_EVENT, "dynamic"}
    _assert_reconciles(rep)


def test_fork_main_does_not_inflate_own_main():
    runs = [run(1, "main"), run(2, "main", "pull_request", head="contrib/r")]
    jobs = {1: [job(["ubuntu-latest"], 60)], 2: [job(["ubuntu-latest"], 600)]}
    rep = build_report("o/r", "x", runs, jobs)
    b = {x.key: x.billed_minutes for x in rep.branches}
    assert b == {"main": 1, "contrib:main": 10}
    assert "pull request from a fork" in render.text(rep, by=["branch"])


def test_demo_reconciles():
    runs, jobs = sample()
    rep = build_report("example/app", "2026-10-01", runs, jobs, private=True)
    _assert_reconciles(rep)
    assert len(rep.branches) > 10
    assert rep.branches[0].key == "main"
    assert {"push", "pull_request", "schedule", "merge_group", "workflow_dispatch"} == {x.key for x in rep.events}


# --- folding the long tail ------------------------------------------------------------------------

def _lines(n):
    out = []
    for i in range(n):
        x = Line(f"b{i}")
        x.runs, x.jobs, x.billed_minutes, x.cost, x.rerun_cost = 1, 2, 10 - i * 0.1, 1.0 - i * 0.01, 0.1
        x.by_sku = {"linux": 10 - i * 0.1}
        out.append(x)
    return out


def test_collapse_folds_tail_into_other_row_that_sums():
    lines = _lines(25)
    shown, other = collapse(lines, 10, "branches")
    assert [x.key for x in shown] == [f"b{i}" for i in range(10)]
    assert other.key == "15 other branches"
    assert other.runs == 15 and other.jobs == 30
    assert _sum(shown, "cost") + other.cost == pytest.approx(_sum(lines, "cost"))
    assert _sum(shown, "billed_minutes") + other.billed_minutes == pytest.approx(_sum(lines, "billed_minutes"))
    assert other.by_sku["linux"] == pytest.approx(sum(x.by_sku["linux"] for x in lines[10:]))


def test_collapse_shows_a_single_leftover_instead_of_other_1():
    shown, other = collapse(_lines(11), 10, "branches")
    assert len(shown) == 11 and other is None
    shown, other = collapse(_lines(3), 10, "events")
    assert len(shown) == 3 and other is None
    shown, other = collapse([], 10, "events")
    assert shown == [] and other is None


def test_text_table_rows_add_up_to_total():
    runs, jobs = sample()
    rep = build_report("example/app", "2026-10-01", runs, jobs, private=True)
    out = render.text(rep, top=4, by=["branch"])
    table = out.split("BY BRANCH", 1)[1].split("\n\n", 1)[0].strip().splitlines()[1:]
    assert table[-1].strip().startswith("(owner:branch")
    rows = table[:-1]
    assert len(rows) == 5 and rows[-1].lstrip().startswith(f"{len(rep.branches) - 4} other branches")
    cents = sum(round(float(r.split("$")[1].split()[0].replace(",", "")) * 100) for r in rows)
    assert abs(cents - round(rep.total.cost * 100)) <= len(rows)  # per-row rounding only


# --- formats --------------------------------------------------------------------------------------

def _demo():
    runs, jobs = sample()
    return build_report("example/app", "2026-10-01", runs, jobs, private=True)


def test_text_sections_only_when_asked_and_in_order():
    rep = _demo()
    plain = render.text(rep)
    assert "BY BRANCH" not in plain and "BY EVENT" not in plain
    both = render.text(rep, by=["event", "branch"])
    assert both.index("BY WORKFLOW") < both.index("BY EVENT") < both.index("BY BRANCH") < both.index("TOP ")


def test_text_long_branch_keeps_its_tail():
    rep = _demo()
    out = render.text(rep, top=20, by=["branch"])
    assert "esbuild-0.25.10" in out and "…" in out
    for line in out.splitlines():
        assert len(line) <= 90


def test_headers_line_up_with_columns():
    rep = _demo()
    lines = render.text(rep, by=["event"]).splitlines()
    head = next(x for x in lines if x.lstrip().startswith("BY EVENT"))
    row = lines[lines.index(head) + 1]
    assert head.index("share") + len("share") == row.index("%") + 1
    money = f"${rep.events[0].cost:,.2f}"
    assert head.index("cost") + len("cost") == row.index(money) + len(money)
    assert head.index("runs") + len("runs") == row.index(f" {rep.events[0].runs} ") + 1 + len(str(rep.events[0].runs))


def test_markdown_tables():
    rep = _demo()
    md = render.markdown(rep, top=5, by=["branch", "event"])
    assert "| Branch | Runs | Billed min | Cost | Share |" in md
    assert "| Event | Runs | Billed min | Cost | Share |" in md
    assert "| `main` |" in md and "| `pull_request` |" in md
    assert "_18 other branches_" in md
    assert "pull request from a fork" in md  # octo-contrib:main is in the top 5
    assert "pull request from a fork" not in render.markdown(rep, top=3, by=["branch"])  # folded away
    assert "| Branch |" not in render.markdown(rep)


def test_markdown_escapes_pipes_and_placeholders_are_plain():
    runs = [run(1, "weird|name"), {"id": 2, "name": "CI"}]
    jobs = {1: [job(["ubuntu-latest"], 60)], 2: [job(["ubuntu-latest"], 60)]}
    md = render.markdown(build_report("o/r", "x", runs, jobs), by=["branch", "event"])
    assert "`weird\\|name`" in md
    assert f"| {NO_BRANCH} |" in md and f"| {UNKNOWN_EVENT} |" in md


def test_json_full_lists_only_when_asked():
    rep = _demo()
    d = json.loads(render.as_json(rep, by=["branch", "event"]))
    assert len(d["branches"]) == len(rep.branches)  # JSON is never folded
    assert sum(x["billed_minutes"] for x in d["branches"]) == d["total"]["billed_minutes"]
    assert d["events"][0]["name"] == rep.events[0].key
    assert "billed_minutes_by_runner" in d["events"][0]
    plain = json.loads(render.as_json(rep))
    assert "branches" not in plain and "events" not in plain


def test_csv_levels():
    rep = _demo()
    rows = list(csv.DictReader(io.StringIO(render.as_csv(rep, by=["branch", "event"]))))
    levels = {r["level"] for r in rows}
    assert levels == {"workflow", "job", "branch", "event"}
    assert sum(float(r["billed_minutes"]) for r in rows if r["level"] == "branch") == rep.total.billed_minutes
    assert sum(1 for r in rows if r["level"] == "branch") == len(rep.branches)
    assert {r["level"] for r in csv.DictReader(io.StringIO(render.as_csv(rep)))} == {"workflow", "job"}


# --- org roll-up ----------------------------------------------------------------------------------

def test_org_groups_events_across_repos_and_prefixes_branches():
    a = build_report("acme/api", "x", [run(1, "main", "push", base="acme/api", head="acme/api")],
                     {1: [job(["ubuntu-latest"], 60)]}, private=True)
    b = build_report("acme/web", "x", [run(2, "main", "push", base="acme/web", head="acme/web"),
                                       run(3, "main", "pull_request", base="acme/web", head="bob/web")],
                     {2: [job(["macos-latest"], 60)], 3: [job(["ubuntu-latest"], 120)]}, private=True)
    org = build_org_report("acme", "x", [a, b], repo_scanned=2)
    assert [x.key for x in org.branches] == ["web › main", "web › bob:main", "api › main"]
    ev = {x.key: x for x in org.events}
    assert ev["push"].runs == 2 and ev["push"].billed_minutes == 2
    assert ev["pull_request"].billed_minutes == 2
    for lines in (org.repos, org.branches, org.events):
        assert _sum(lines, "billed_minutes") == org.total.billed_minutes
        assert _sum(lines, "cost") == pytest.approx(org.total.cost)
    txt = render.org_text(org, by=["event", "branch"])
    assert "BY EVENT" in txt and "web › bob:main" in txt and "pull request from a fork" in txt
    assert "| `web › main` |" in render.org_markdown(org, by=["branch"])
    assert json.loads(render.as_json(org, by=["event"]))["events"][0]["name"] == "push"
    assert "event,push" in render.org_csv(org, by=["event"])


# --- CLI ------------------------------------------------------------------------------------------

def test_cli_by_flag_forms(capsys):
    assert main(["demo", "--by", "branch,event"]) == 0
    out = capsys.readouterr().out
    assert "BY BRANCH" in out and "BY EVENT" in out
    assert main(["demo", "--by", "event", "--by", "branches", "--by", "event"]) == 0
    out = capsys.readouterr().out
    assert out.count("BY EVENT") == 1 and out.index("BY EVENT") < out.index("BY BRANCH")
    assert main(["demo", "--by", "Branch event", "--format", "json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert "branches" in d and "events" in d


def test_cli_by_typo_suggests(capsys):
    with pytest.raises(SystemExit) as e:
        main(["demo", "--by", "evnt"])
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "did you mean 'event'?" in err


def test_cli_by_unknown_and_top_validation(capsys):
    with pytest.raises(SystemExit) as e:
        main(["demo", "--by", "workflow"])
    assert e.value.code == 2
    assert "use branch, event, or branch,event" in capsys.readouterr().err
    with pytest.raises(SystemExit) as e:
        main(["demo", "--top", "0"])
    assert e.value.code == 2
    assert "must be 1 or more" in capsys.readouterr().err


def test_cli_help_mentions_by(capsys):
    for cmd in ("report", "org"):
        with pytest.raises(SystemExit):
            main([cmd, "--help"])
        out = capsys.readouterr().out
        assert "--by branch|event" in out and "pull_request" in out
