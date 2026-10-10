# Command reference

```text
runbill [report] [OWNER/REPO] [options]
runbill demo [--format text|md|json|csv]
runbill rates
runbill --version
```

| Option | Default | |
|---|---|---|
| `--days N` | 30 | look back N days |
| `--since YYYY-MM-DD` | | start date, overrides `--days` |
| `--workflow FILE` | | only this workflow (`ci.yml` or id) |
| `--branch NAME` | | only runs on this branch |
| `--max-runs N` | 500 | stop after N runs |
| `--top N` | 10 | rows per table |
| `--rate SKU=USD` | | override a tariff, repeatable |
| `--format` | `text` | `text`, `md`, `json`, `csv` |
| `-o, --output FILE` | stdout | write to a file (appends if it is `$GITHUB_STEP_SUMMARY`) |
| `--fail-over USD` | | exit 3 if the total estimate is above USD |

Exit codes: `0` ok, `1` GitHub API error, `2` usage error, `3` over budget.

## JSON shape

```json
{"repo": "o/r", "since": "2026-09-10", "private": true, "runs": 97, "truncated": false,
 "total": {"name": "total", "runs": 97, "jobs": 320, "raw_minutes": 1510.2, "billed_minutes": 2260,
           "cost_usd": 42.86, "rerun_cost_usd": 5.4, "billed_minutes_by_runner": {"linux": 1270, "macos": 490}},
 "rerun_share": 0.126, "workflows": [...], "jobs": [...]}
```
