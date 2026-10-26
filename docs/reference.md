# Command reference

```text
runbill [report] [OWNER/REPO] [options]
runbill org ORG [options]
runbill demo [--format text|md|json|csv] [--top N] [--by branch|event] [--compare]
runbill rates
runbill --version
```

`org` takes an org or user login (not `OWNER/REPO`). Extra flag: `--include-archived`.
`--max-runs` defaults to 200 and applies per repo. `--workflow` / `--branch` are report-only; `--by` works
in both (org branch rows are `repo › branch`).

| Option | Default | |
|---|---|---|
| `--days N` | 30 | look back N days |
| `--since YYYY-MM-DD` | | start date, overrides `--days` |
| `--workflow FILE` | | only this workflow (`ci.yml` or id) |
| `--branch NAME` | | only runs on this branch |
| `--max-runs N` | 500 | stop after N runs |
| `--top N` | 10 | rows per table; with `--by`, the rest are summed into one `N other …` row |
| `--by branch`, `--by event` | | add a per-branch and/or per-trigger-event table; `--by branch,event` for both (repeatable) |
| `--rate SKU=USD` | | override a tariff, repeatable |
| `--format` | `text` | `text`, `md`, `json`, `csv` |
| `-o, --output FILE` | stdout | write to a file (appends if it is `$GITHUB_STEP_SUMMARY`) |
| `--fail-over USD` | | exit 3 if the total estimate is above USD |
| `--compare` | | diff the window against the equal-length window right before it (per workflow, job, repo, and `--by` rows) |
| `--fail-increase PCT` | | with `--compare`: exit 3 if total cost rose more than PCT percent (`25` or `25%`) |

Exit codes: `0` ok, `1` GitHub API error, `2` usage error (including a bad `--by`, `--top`, `--since` in the future, or `--fail-increase` without `--compare`), `3` over budget or over the allowed increase.

## JSON shape

Repo report:

```json
{"repo": "o/r", "since": "2026-09-10", "private": true, "runs": 97, "truncated": false,
 "total": {"name": "total", "runs": 97, "jobs": 320, "raw_minutes": 1509.68, "billed_minutes": 1672,
           "cost_usd": 42.466, "rerun_cost_usd": 5.4,
           "billed_minutes_by_runner": {"linux": 479, "linux-8-core": 196, "macos": 490, "self-hosted": 17, "windows": 490}},
 "rerun_share": 0.1272, "workflows": [...], "jobs": [...]}
```

With `--by branch` / `--by event`, the report also has `"branches"` / `"events"`: every branch or event (no
`other` folding), ranked by cost, in the same shape as `workflows`. CSV gets rows with `level` `branch` / `event`.

```json
{"branches": [{"name": "main", "runs": 52, "jobs": 155, "raw_minutes": 779.27, "billed_minutes": 862,
               "cost_usd": 20.806, "rerun_cost_usd": 5.4, "billed_minutes_by_runner": {...}},
              {"name": "octo-contrib:main", "runs": 4, ...}],
 "events": [{"name": "pull_request", "runs": 41, ...}, {"name": "push", "runs": 40, ...}]}
```

Org report (`runbill org`):

```json
{"org": "acme", "since": "2026-09-10", "private": true, "runs": 200, "truncated": false,
 "repo_scanned": 12, "repo_active": 5, "public_repos": 1, "private_repos": 4,
 "total": {...}, "rerun_share": 0.1, "repos": [{"name": "acme/app", "runs": 97, ...}, ...]}
```

Comparison (`--compare`): both windows with their own totals, then one row per workflow / job (or repo for
`org`, plus `branches` / `events` with `--by`), sorted by `delta.cost_usd`, never folded. `status` is
`new`, `gone`, `up`, `down` or `flat`; `cost_pct` is `null` when the earlier cost was $0.

```json
{"repo": "example/app", "private": true,
 "compare": {"previous": {"from": "2026-09-24T09:00:00Z", "to": "2026-10-01T09:00:00Z", "days": 7.0,
                          "runs": 93, "truncated": false, "total": {"billed_minutes": 1021.0, "cost_usd": 8.262, ...}},
             "current":  {"from": "2026-10-01T09:00:00Z", "to": "2026-10-08T09:00:00Z", "days": 7.0,
                          "runs": 97, "truncated": false, "total": {...}}},
 "total": {"name": "total", "status": "up",
           "previous": {"runs": 93, "jobs": 207, "billed_minutes": 1021.0, "cost_usd": 8.262},
           "current":  {"runs": 97, "jobs": 320, "billed_minutes": 1672.0, "cost_usd": 42.466},
           "delta":    {"runs": 4, "jobs": 113, "billed_minutes": 651.0, "cost_usd": 34.204, "cost_pct": 413.99}},
 "workflows": [{"name": "CI", "status": "up", "previous": {...}, "current": {...},
                "delta": {"billed_minutes": 698.0, "cost_usd": 32.076, "cost_pct": 560.38, ...}},
               {"name": "Benchmarks", "status": "gone", ...}],
 "jobs": [...]}
```

CSV: `level,name,status,runs_before,runs_now,jobs_before,jobs_now,billed_minutes_before,billed_minutes_now,cost_usd_before,cost_usd_now,delta_billed_minutes,delta_cost_usd,delta_cost_pct`,
total row first.
