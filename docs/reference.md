# Command reference

```text
runbill [report] [OWNER/REPO] [options]
runbill org ORG [options]
runbill demo [--format text|md|json|csv]
runbill rates
runbill --version
```

`org` takes an org or user login (not `OWNER/REPO`). Extra flag: `--include-archived`.
`--max-runs` defaults to 200 and applies per repo. `--workflow` / `--branch` are report-only.

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

Repo report:

```json
{"repo": "o/r", "since": "2026-09-10", "private": true, "runs": 97, "truncated": false,
 "total": {"name": "total", "runs": 97, "jobs": 320, "raw_minutes": 1509.68, "billed_minutes": 1672,
           "cost_usd": 42.466, "rerun_cost_usd": 5.4,
           "billed_minutes_by_runner": {"linux": 479, "linux-8-core": 196, "macos": 490, "self-hosted": 17, "windows": 490}},
 "rerun_share": 0.1272, "workflows": [...], "jobs": [...]}
```

Org report (`runbill org`):

```json
{"org": "acme", "since": "2026-09-10", "private": true, "runs": 200, "truncated": false,
 "repo_scanned": 12, "repo_active": 5, "public_repos": 1, "private_repos": 4,
 "total": {...}, "rerun_share": 0.1, "repos": [{"name": "acme/app", "runs": 97, ...}, ...]}
```
