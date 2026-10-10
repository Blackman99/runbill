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
```

## Reading the report

- **billed min**: per job, `ceil(duration in minutes)`, summed (as GitHub bills; larger runners are priced by their own per-minute rate, not by more minutes). Skipped jobs and zero-length jobs are ignored.
- **raw min**: actual wall-clock job time, unrounded. A large gap between raw and billed means many short jobs (a wide matrix of 20-second jobs costs a minute each).
- **cost**: billed minutes × the tariff for that runner (see [Configuration](config.md)).
- **re-runs**: cost from jobs with `run_attempt > 1`, as a share of total.
- **share**: the workflow's part of the total cost.

On a **public** repo standard runners are free; runbill says so and shows what the same minutes would cost on a private repo.

## API cost

One request per page of runs (100 runs) plus one per run for its jobs. `--max-runs` (default 500) caps it; runbill tells you when it stopped early.
