# Usage

```bash
runbill OWNER/REPO                 # last 30 days
runbill                            # repo from GITHUB_REPOSITORY or git origin
runbill OWNER/REPO --days 7 --top 20
runbill OWNER/REPO --since 2026-09-01
runbill OWNER/REPO --workflow ci.yml --branch main
runbill OWNER/REPO --format md -o report.md
runbill OWNER/REPO --format csv > minutes.csv
runbill OWNER/REPO --fail-over 50  # exit 3 if the estimate is over $50

# whole org or user — repos ranked by cost
runbill org your-org --days 30
runbill org your-org --since 2026-09-01 --top 20 --format md
runbill org your-user --max-runs 100 --fail-over 200
```

## Org rollup

`runbill org ORG` lists every non-archived repo for that org or user, pulls Actions runs
in the window for each one that has activity, and prints a single table ranked by cost.
Org totals are the sum of the per-repo totals. Archived repos are skipped unless you pass
`--include-archived`.

`--max-runs` is **per repo** (default 200 for `org`, 500 for a single-repo report). An org
scan hits the API once per page of runs plus once per run for its jobs, across every repo,
with up to four repos in flight — so it burns the rate limit faster than a single-repo
report. If you get a 403 rate-limit error, narrow `--days` / `--max-runs` or use a token
with a higher quota.

## Reading the report

- **billed min**: per job, `ceil(duration in minutes)`, summed (as GitHub bills; larger runners are priced by their own per-minute rate, not by more minutes). Skipped jobs and zero-length jobs are ignored.
- **raw min**: actual wall-clock job time, unrounded. A large gap between raw and billed means many short jobs (a wide matrix of 20-second jobs costs a minute each).
- **cost**: billed minutes × the tariff for that runner (see [Configuration](config.md)).
- **re-runs**: cost from jobs with `run_attempt > 1`, as a share of total.
- **share**: the workflow's part of the total cost.

On a **public** repo standard runners are free; runbill says so and shows what the same minutes would cost on a private repo.

## API cost

One request per page of runs (100 runs) plus one per run for its jobs. `--max-runs` (default 500) caps it; runbill tells you when it stopped early.
