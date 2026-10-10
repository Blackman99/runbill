import json

from runbill import render
from runbill.cli import main
from runbill.core import DEFAULT_RATES, build_report, classify_runner, job_seconds
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
    assert classify_runner({"labels": ["ubuntu-latest-8-cores"]}) == ("linux-8-core", 1.0)
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


def _c(*labels):
    return classify_runner({"labels": list(labels)})


def test_larger_runners_use_published_rates():
    # https://docs.github.com/en/billing/reference/actions-runner-pricing
    assert DEFAULT_RATES["linux-8-core"] == 0.022
    assert DEFAULT_RATES["windows-4-core"] == 0.022
    assert DEFAULT_RATES["linux-arm-4-core"] == 0.008
    assert _c("ubuntu-22.04-4-cores") == ("linux-4-core", 1.0)
    assert _c("linux_16_core") == ("linux-16-core", 1.0)
    assert _c("ubuntu-24.04-arm-8-core") == ("linux-arm-8-core", 1.0)
    assert _c("windows-latest-8-cores") == ("windows-8-core", 1.0)
    assert _c("windows-11-arm-2-core") == ("windows-arm-2-core", 1.0)
    assert _c("windows-11-arm") == ("windows-arm", 1.0)
    assert _c("ubuntu-latest-2-cores") == ("linux", 1.0)  # 2-core advanced = standard rate
    assert _c("linux-gpu-4-core") == ("linux-gpu", 1.0)


def test_macos_larger_and_slim():
    assert _c("macos-15-large") == ("macos-large", 1.0)
    assert _c("macos-latest-xlarge") == ("macos-xlarge", 1.0)
    assert _c("xcode-27-xlarge") == ("macos-xlarge", 1.0)
    assert _c("macos-latest") == ("macos", 1.0)
    assert _c("ubuntu-slim") == ("linux-slim", 1.0)
    assert DEFAULT_RATES["linux-slim"] == 0.002


def test_unpublished_size_falls_back_to_multiplier():
    assert _c("ubuntu-latest-12-cores") == ("linux", 6.0)


def test_larger_runner_cost_is_minutes_times_size_rate():
    runs = [{"id": 1, "name": "CI"}]
    jobs = {1: [{"name": "big", "labels": ["ubuntu-latest-8-cores"], "run_attempt": 1, "conclusion": "success",
                 "started_at": "2026-10-01T00:00:00Z", "completed_at": "2026-10-01T00:09:30Z"}]}
    rep = build_report("o/r", "2026-10-01", runs, jobs)
    assert rep.total.billed_minutes == 10
    assert round(rep.total.cost, 4) == 0.22
    assert rep.total.by_sku == {"linux-8-core": 10}
