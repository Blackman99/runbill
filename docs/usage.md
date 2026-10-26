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
runbill OWNER/REPO --compare --days 7       # this week vs last week, per workflow and job
runbill OWNER/REPO --compare --fail-increase 25   # exit 3 if cost rose more than 25%

# whole org or user — repos ranked by cost
runbill org your-org --days 30
runbill org your-org --since 2026-09-01 --top 20 --format md
runbill org your-user --max-runs 100 --fail-over 200
runbill org your-org --by event               # triggers ranked by cost across all repos
runbill org your-org --compare --days 7       # which repo got more expensive this week
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

## Week over week

`--compare` answers "what got more expensive?". It splits time into two windows of the same length that
touch: the one you asked for (`--days N` or `--since DATE`, ending now) and the one right before it. Every
workflow and job gets billed minutes and cost for both, the change in dollars and percent, and the rows are
sorted by **biggest cost increase first**:

```console
$ runbill demo --compare --top 4
runbill · example/app · last 7 days vs the 7 days before

  now     2026-10-01 09:00 → 2026-10-08 09:00 UTC   97 runs
  before  2026-09-24 09:00 → 2026-10-01 09:00 UTC   93 runs

  TOTAL   $8.26 → $42.47   +$34.20 (+414.0%)   billed min 1,021 → 1,672 (+651)
  Biggest increase: CI +$32.08 (+560.4%), led by test (macos) +$30.38 (new).

  BY WORKFLOW                   min before   min now  cost before   cost now      Δ cost      Δ %
  CI                                   702     1,400        $5.72     $37.80     +$32.08  +560.4%
  E2E nightly                          153       196        $0.92      $4.31      +$3.39  +369.7%
  Release                                –        26            –      $0.05      +$0.05      new
  Docs                                  62        50        $0.37      $0.30      -$0.07   -19.4%
  Benchmarks                           104         –        $1.25          –      -$1.25     gone

  BY JOB                        min before   min now  cost before   cost now      Δ cost      Δ %
  CI › test (macos)                      –       490            –     $30.38     +$30.38      new
  E2E nightly › playwright             153       196        $0.92      $4.31      +$3.39  +369.7%
  CI › test (windows)                  378       490        $3.78      $4.90      +$1.12   +29.6%
  CI › test (ubuntu)                   270       350        $1.62      $2.10      +$0.48   +29.6%
  5 other jobs (2 new, 1 gone)         220       146        $1.94      $0.77      -$1.17   -60.2%

  Sorted by Δ cost, biggest increase first. new = no runs before; gone = no runs now.
  List-price estimate. Jobs rounded up to whole minutes; runner type and size from labels.
```

- **Equal windows.** `--days 7` compares the last 7×24 hours with the 7×24 hours before that (both to the
  minute, in UTC), so a busy Monday never lands on only one side. `--since 2026-10-01` compares
  2026-10-01 00:00 UTC → now with the same length of time before it. Because the window ends at the current
  minute rather than at the start of a day, the "now" totals can differ slightly from a plain report.
- **new / gone.** A workflow or job that only ran in the current window is `new`; one that only ran before
  is `gone` (deleted workflow, removed matrix leg, renamed job). A row that existed before but cost $0 (e.g. a
  self-hosted job) and now costs money shows `from $0` rather than a made-up percentage.
- **One fetch.** runbill pulls runs once, back to the start of the earlier window, and files each run under a
  window by its `created_at`. `--max-runs` applies **per window**; if the cap is hit before reaching the start
  of the earlier window, runbill warns that the "before" side is incomplete and increases are overstated.
- **Folding.** `--top` keeps the biggest movers and sums the rest into one `N other workflows (2 new, 1 gone)`
  row, so the table still adds up. JSON and CSV list every row.
- **`--by branch,event`** adds the same before/now diff per branch and per trigger event.
- **`runbill org ORG --compare`** diffs repos instead of workflows: a repo with no runs before is `new`.
- **Gate.** `--fail-increase PCT` exits 3 when total cost rose by more than PCT percent (`25` or `25%`) and
  needs `--compare` (without it runbill stops with a usage error). If the earlier window cost $0, runbill notes it and does
  not fail. `--fail-over USD` still applies to the current window.

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
