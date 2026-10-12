# Roadmap

## v0.1 (now)
- Per-workflow and per-job billed minutes/cost from runs + jobs API; per-job round-up; runner tariff from labels
- Re-run share; text/md/json/csv; `--fail-over` budget gate; composite GitHub Action with job summary

## v0.2
- ~~`runbill org ORG`: roll up across all repos of an org/user, ranked by cost~~ (shipped)
- Per-branch and per-event (push / pull_request / schedule) breakdown
- Week-over-week diff (`--compare`) to catch a workflow that suddenly got expensive

## v0.3
- Import GitHub's billing usage-report CSV to calibrate rates against the real invoice
- Hints: matrix legs under 1 minute (rounding waste), macOS jobs that could run on Linux, long-running schedules
- PR comment mode: estimated cost of the PR's CI runs

## Later
- Cache API responses between runs; GHES polish; PyPI release
