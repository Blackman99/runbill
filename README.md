<p align="center"><img src="site/logo-512.png" width="96" alt="runbill logo"></p>

# runbill

**Which GitHub Actions workflow and job is eating your minutes?**

GitHub's billing page shows one total. The per-workflow `timing` API that used to break it down is
[closing down](https://github.blog/changelog/2025-02-02-actions-get-workflow-usage-and-get-workflow-run-usage-endpoints-closing-down/).
runbill rebuilds the breakdown from the runs and jobs API: billed minutes and estimated cost per workflow
and per job, each job rounded up to the minute the way GitHub bills, with the runner tariff read from labels
(Linux / Windows / macOS / arm / larger runners / self-hosted) and the share of cost spent on re-runs.

![runbill on astral-sh/uv](site/demo.gif)

## Install

```bash
pipx install git+https://github.com/Blackman99/runbill    # Python 3.9+, no dependencies
```

Uses `GH_TOKEN` / `GITHUB_TOKEN` or your `gh` login (needs `actions:read`).

## Usage

```console
$ runbill your-org/app --days 30
runbill · your-org/app · runs since 2026-09-10 (97 runs, 320 jobs)

  TOTAL          1,672 billed min       $42.47   (raw 1,510 min, re-runs 12.7%)

  BY WORKFLOW                              runs    billed min        cost   share
  CI                                          60         1,400      $37.80   89.0%
  E2E nightly                                  9           196       $4.31   10.2%
  ...
  TOP 8 JOBS                               jobs    billed min        cost
  CI › test (macos)                           70           490      $30.38
  CI › test (windows)                         70           490       $4.90
```

`--format md|json|csv`, `--workflow ci.yml`, `--rate macos=0.08`, `--fail-over 50` (exit 3 over budget).

As a GitHub Action (writes the report to the job summary):

```yaml
permissions: { actions: read, contents: read }
steps:
  - uses: Blackman99/runbill@v0.1.0
    with: { days: 7, fail-over: 20 }
```

Docs: **https://blackman99.github.io/runbill/docs/** · Estimates at list price, not an invoice. MIT.
