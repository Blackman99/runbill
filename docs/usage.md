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
runbill OWNER/REPO --by branch,event        # add per-branch and per-trigger tables
runbill OWNER/REPO --by event --format md   # just the trigger table, as Markdown

# whole org or user — repos ranked by cost
runbill org your-org --days 30
runbill org your-org --since 2026-09-01 --top 20 --format md
runbill org your-user --max-runs 100 --fail-over 200
runbill org your-org --by event               # triggers ranked by cost across all repos
```

## By branch and by event

`--by branch`, `--by event`, or both (`--by branch,event`, or repeat the flag) add tables that split the
same bill by the run's **head branch** and by its **trigger event**:

```console
$ runbill your-org/app --by branch,event --top 4
  BY BRANCH                                 runs    billed min        cost   share
  main                                        52           862      $20.81   49.0%
  feat/checkout-v2                             9           180       $4.86   11.4%
  fix/flaky-login-test                         6           120       $3.24    7.6%
  octo-contrib:main                            4            80       $2.16    5.1%
  19 other branches                           26           430      $11.40   26.8%
  (owner:branch = pull request from a fork)

  BY EVENT                                  runs    billed min        cost   share
  pull_request                                41           730      $19.50   45.9%
  push                                        40           640      $16.44   38.7%
  schedule                                     9           196       $4.31   10.2%
  merge_group                                  4            80       $2.16    5.1%
  workflow_dispatch                            3            26       $0.05    0.1%
```

- **Same billing rules.** Each job is still rounded up to the whole minute on its own and priced at its
  runner's rate; those minutes are then filed under the run's branch and event. Every job lands in exactly one
  row, so each table adds up to the TOTAL line (billed minutes exactly; cost up to per-row cent rounding).
- **Ranked by cost**, like every other table. The rows after `--top` are summed into one
  `N other branches` row, so a repo with hundreds of short-lived PR branches stays readable and the table
  still adds up. JSON and CSV are never folded: they list every branch and event.
- **Fork pull requests** show as `owner:branch` (the way GitHub's PR header writes it), so a contributor's
  fork `main` is not counted as your `main`. Git branch names can't contain `:`, so this never collides
  with a real branch.
- **Tag pushes** appear under the tag name (`v1.2.0`): that is what GitHub reports as the run's branch.
- **Events** are whatever GitHub sends: `push`, `pull_request`, `pull_request_target`, `schedule`,
  `workflow_dispatch`, `merge_group`, `release`, `workflow_run`, `dynamic` (Dependabot, Pages, Copilot and
  other GitHub-managed runs), and any new ones, under their own name.
- A run with no branch or no event (rare, e.g. some deleted or GitHub-internal runs) is grouped under
  `(no branch)` / `(unknown event)` rather than dropped.
- In `runbill org`, events are summed across repos and branches are written `repo › branch`.
- `--branch NAME` (a filter) and `--by branch` (a breakdown) combine: filter to `main`, then split it by event.

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
- **share**: the row's part of the total cost.

On a **public** repo standard runners are free; runbill says so and shows what the same minutes would cost on a private repo.

## API cost

One request per page of runs (100 runs) plus one per run for its jobs. `--max-runs` (default 500) caps it; runbill tells you when it stopped early.
