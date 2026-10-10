import json

from runbill import render
from runbill.cli import main
from runbill.core import build_report, classify_runner, job_seconds
from runbill.demo import sample


def job(labels, secs, attempt=1, conclusion="success", name="j"):
    m, s = divmod(secs, 60)
    return {"name": name, "labels": labels, "run_attempt": attempt, "conclusion": conclusion,
            "started_at": "2026-10-01T00:00:00Z", "completed_at": f"2026-10-01T00:{m:02d}:{s:02d}Z"}


def test_classify():
    assert classify_runner({"labels": ["ubuntu-latest"]}) == ("linux", 1.0)
    assert classify_runner({"labels": ["macos-14"]}) == ("macos", 1.0)
    assert classify_runner({"labels": ["windows-2022"]}) == ("windows", 1.0)
    assert classify_runner({"labels": ["ubuntu-24.04-arm"]}) == ("linux-arm", 1.0)
    assert classify_runner({"labels": ["ubuntu-latest-8-cores"]}) == ("linux", 4.0)
    assert classify_runner({"labels": ["self-hosted", "linux", "x64"]}) == ("self-hosted", 1.0)


def test_round_up_per_job_and_skips():
    runs = [{"id": 1, "name": "CI"}]
    jobs = {1: [job(["ubuntu-latest"], 61), job(["ubuntu-latest"], 1),
                job(["ubuntu-latest"], 500, conclusion="skipped")]}
    r = build_report("o/r", "2026-10-01", runs, jobs)
    assert r.total.billed_minutes == 3  # 2 + 1, skipped ignored
    assert abs(r.total.cost - 3 * 0.006) < 1e-9
    assert job_seconds(jobs[1][0]) == 61


def test_reruns_and_rates_and_ordering():
    runs = [{"id": 1, "name": "cheap"}, {"id": 2, "name": "mac"}]
    jobs = {1: [job(["ubuntu-latest"], 120)],
            2: [job(["macos-latest"], 60), job(["macos-latest"], 60, attempt=2)]}
    r = build_report("o/r", "x", runs, jobs, rates={"macos": 0.1})
    assert r.workflows[0].key == "mac"
    assert abs(r.total.rerun_cost - 0.1) < 1e-9
    assert r.as_dict()["rerun_share"] > 0.4


def test_demo_and_formats(capsys):
    runs, jobs = sample()
    r = build_report("example/app", "2026-10-01", runs, jobs, private=True)
    assert r.workflows[0].key == "CI"
    assert "| CI |" in render.markdown(r)
    assert json.loads(render.as_json(r))["runs"] == 97
    assert render.as_csv(r).startswith("level,name")
    assert main(["demo"]) == 0
    assert "TOTAL" in capsys.readouterr().out


def test_public_note():
    r = build_report("o/r", "x", [], {}, private=False)
    assert "free" in render.text(r)
