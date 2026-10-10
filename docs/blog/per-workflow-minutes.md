---
title: "GitHub took away per-workflow minutes. Here's how to get them back"
description: GitHub's per-workflow Actions usage endpoint is closing down and the billing page shows totals by SKU and repo. Here is how to rebuild per-workflow and per-job billed minutes from the runs and jobs API, and a tool that does it.
---

# GitHub took away per-workflow minutes. Here's how to get them back

*October 2026 · [中文](per-workflow-minutes-zh.md)*

Your Actions bill went up this month. The billing page tells you by how much, per repository and per runner type.
It does not tell you *which workflow* did it, let alone which job, or how much of it was re-running a flaky test
suite until it went green.

There used to be an API for the first part. It is going away.

## What changed

**The per-workflow usage endpoints are closing down.** `GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}/timing`
("Get workflow usage") and the per-run equivalent are
[closing down](https://github.blog/changelog/2025-02-02-actions-get-workflow-usage-and-get-workflow-run-usage-endpoints-closing-down/)
as accounts move to GitHub's new billing platform. GitHub's changelog points to the billing usage endpoint instead,
which "summarizes Actions usage by SKU, organization, and repository, however it does not provide detailed workflow
information". Workflow detail now lives in the usage report you request from the billing page, which is emailed to
you ([Viewing usage](https://docs.github.com/en/billing/how-tos/products/view-productlicense-use)).

Even before that, the endpoint was not the billing view. Its own
[reference page](https://docs.github.com/en/rest/actions/workflows#get-workflow-usage) says the usage "does not include
the multiplier for macOS and Windows runners and is not rounded up to the nearest whole minute", and it only covered
private repositories on GitHub-hosted runners. There was never a job-level view.

**Prices changed, too.** On 1 January 2026 GitHub
[reduced hosted-runner prices by up to 39%](https://github.blog/changelog/2026-01-01-reduced-pricing-for-github-hosted-runners-usage/).
A $0.002/min "cloud platform charge" for self-hosted runners, announced for 1 March 2026, was
[postponed](https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/)
("to take time to re-evaluate our approach"). The current
[billing docs](https://docs.github.com/en/billing/concepts/product-billing/github-actions) still say Actions usage is
free for self-hosted runners and for public repositories on standard GitHub-hosted runners.

So: cheaper per minute, but less visibility into where the minutes go.

## How GitHub actually bills a job

Everything you need to rebuild the breakdown is in the
[runner pricing reference](https://docs.github.com/en/billing/reference/actions-runner-pricing):

1. **Per job, rounded up.** "GitHub rounds the minutes and partial minutes each job uses up to the nearest whole
   minute." A 10-second lint job is a billed minute. A matrix of 20 short jobs is at least 20 minutes.
2. **Per runner type.** Each runner has its own per-minute rate. Current list prices for standard runners:

    | Runner | Billing SKU | $/min |
    |---|---|---|
    | Linux 2-core (x64) | `actions_linux` | $0.006 |
    | Linux 2-core (arm64) | `actions_linux_arm` | $0.005 |
    | Windows 2-core (x64) | `actions_windows` | $0.010 |
    | macOS 3/4-core | `actions_macos` | $0.062 |

    A macOS minute costs about ten Linux minutes. Larger runners have their own rows (Linux 8-core x64 is $0.022).
3. **Re-runs count.** GitHub's own example: a workflow that fails after 5 minutes and is re-run for 10 minutes uses
   15 minutes ([billing docs](https://docs.github.com/en/billing/concepts/product-billing/github-actions#examples-of-how-usage-is-measured)).
4. **What's free.** Standard hosted runners in public repositories, self-hosted runners, plus your plan's included
   minutes (2,000/month on GitHub Free, 3,000 on Pro and Team, 50,000 on Enterprise Cloud). Larger runners are always
   billed, even on public repositories.

## Rebuilding the breakdown from the API

The ordinary Actions API has what you need, with nothing more than `actions:read`:

- `GET /repos/{owner}/{repo}/actions/runs?created=>=YYYY-MM-DD` lists runs, each with its workflow name and
  `run_attempt`.
- `GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs?filter=all` lists every job of every attempt, with
  `started_at`, `completed_at`, `labels` and `run_attempt`.

For each job: take `completed_at - started_at`, round up to the whole minute, pick the rate from the runner labels
(`macos-14` → macOS, `windows-latest` → Windows, `ubuntu-24.04-arm` → Linux arm64, `self-hosted` → $0), and add it to
its workflow and to its job name. Jobs from attempt 2 and later are re-runs; total them separately. Skip jobs that were
skipped.

That's the whole idea. The fiddly parts are pagination, `filter=all` (otherwise you only see the latest attempt),
label conventions, and remembering that a public repo's bill is $0.

## runbill: the same thing in one command

[runbill](https://github.com/Blackman99/runbill) packages exactly that. It's a Python CLI with no dependencies and also
a GitHub Action. It uses `GH_TOKEN` / `GITHUB_TOKEN` or your `gh` login.

```bash
pipx install git+https://github.com/Blackman99/runbill
runbill your-org/app --days 30
```

Here is a real run against [astral-sh/uv](https://github.com/astral-sh/uv), capped at its newest 80 runs:

```console
$ runbill astral-sh/uv --days 2 --max-runs 80 --top 6
runbill: fetching jobs for 80 runs…
runbill · astral-sh/uv · runs since 2026-10-08 (80 runs, 2100 jobs)

  TOTAL          9,272 billed min      $134.83   (raw 8,055 min, re-runs 17.6%)

  BY WORKFLOW                              runs    billed min        cost   share
  CI                                          18         5,666      $59.50   44.1%
  Debug study calibration block 0              2           497      $13.48   10.0%
  Debug study calibration block 1              2           495      $13.35    9.9%
  Debug study confirmatory block 1002          1           421       $7.92    5.9%
  Debug study confirmatory block 1001          1           411       $7.92    5.9%
  Debug study confirmatory block 1003          1           409       $7.90    5.9%

  TOP 6 JOBS                               jobs    billed min        cost
  Debug study calibration block 0 › macOS      2           180      $11.16
  Debug study calibration block 1 › macOS      2           178      $11.04
  CI › build-release-artifacts / aarch64-a     8            96       $5.95
  Debug study confirmatory block 1001 › ma     1            90       $5.58
  Debug study confirmatory block 1003 › ma     1            90       $5.58
  Debug study confirmatory block 1005 › ma     1            90       $5.58

  ! stopped at --max-runs; totals cover only the newest runs.
  Public repo: standard GitHub-hosted runners are free here. Figures show what these minutes would cost at list price on a private repo.
```

uv is public, so these minutes are free for them; the dollar column is what the same runs would cost at list price on a
private repository. Three things stand out that the billing page would never show:

- **CI is 44% of the cost, not 100%.** Over half the list-price cost in this window came from a handful of one-off
  "Debug study" workflows.
- **The most expensive jobs are macOS jobs.** The top two jobs are 358 billed minutes and $22.20 between them, about
  a sixth of the total, because of the macOS rate.
- **17.6% of the cost was re-runs** (attempt 2 or later).

Rounding matters most on small, fast jobs. runbill's own repository, for the last 7 days:

```console
$ runbill Blackman99/runbill --days 7 --top 3
runbill: fetching jobs for 3 runs…
runbill · Blackman99/runbill · runs since 2026-10-03 (3 runs, 13 jobs)

  TOTAL             13 billed min        $0.14   (raw 3 min, re-runs 0.0%)

  BY WORKFLOW                              runs    billed min        cost   share
  CI                                           1            10       $0.12   87.0%
  Pages                                        1             2       $0.01    8.7%
  Release                                      1             1       $0.01    4.3%

  TOP 3 JOBS                               jobs    billed min        cost
  CI › test (macos-latest, py3.12)             1             1       $0.06
  CI › test (windows-latest, py3.12)           1             1       $0.01
  CI › build                                   1             1       $0.01

  Public repo: standard GitHub-hosted runners are free here. Figures show what these minutes would cost at list price on a private repo.
```

13 jobs with about 3 minutes of run time between them, billed as 13 minutes, because every job is rounded up on its own. On a private repo
with a big matrix of quick jobs, that gap is real money.

Other useful flags: `--workflow ci.yml`, `--branch main`, `--format md|json|csv`, `--rate macos=0.08` to override a
price, and `--fail-over 50` to exit with status 3 when the estimate is over $50.

## Run it in CI, weekly

As an Action it writes the report to the job summary and can fail over a budget:

```yaml
name: Actions minutes
on:
  schedule: [{ cron: "0 1 * * 1" }]   # Mondays
  workflow_dispatch:
permissions: { actions: read, contents: read }
jobs:
  meter:
    runs-on: ubuntu-latest
    steps:
      - uses: Blackman99/runbill@v0.1.0
        with: { days: 7, fail-over: 20 }
```

## What it isn't

runbill is a **list-price estimate**, not invoice reconciliation. It doesn't know your included minutes, discounts or
contract prices. Larger-runner rates are approximated from the core count in the runner label (for example 8-core
Linux is estimated at 4 × $0.006 = $0.024/min, while GitHub lists $0.022), so treat large-runner totals as slightly
high. For the authoritative per-workflow numbers, the billing usage report is still the source; runbill is for finding
*where* the minutes go, from a terminal or a scheduled job, down to the job and the re-run.

Next on the [roadmap](https://github.com/Blackman99/runbill/blob/main/ROADMAP.md): an org-wide rollup
(`runbill org ORG`), per-branch and per-event breakdowns, and a week-over-week `--compare`.

Feedback, especially runner label setups that runbill misclassifies, is welcome in
[issues](https://github.com/Blackman99/runbill/issues).

## Sources

- GitHub Changelog, [Actions Get workflow usage and Get workflow run usage endpoints closing down](https://github.blog/changelog/2025-02-02-actions-get-workflow-usage-and-get-workflow-run-usage-endpoints-closing-down/) (2 Feb 2025)
- GitHub REST docs, [Get workflow usage](https://docs.github.com/en/rest/actions/workflows#get-workflow-usage)
- GitHub Changelog, [Reduced pricing for GitHub-hosted runners usage](https://github.blog/changelog/2026-01-01-reduced-pricing-for-github-hosted-runners-usage/) (1 Jan 2026)
- GitHub Changelog, [Update to GitHub Actions pricing](https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/) (16 Dec 2025, self-hosted charge postponed)
- GitHub Docs, [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- GitHub Docs, [Actions runner pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing)
- GitHub Docs, [Viewing usage of metered products](https://docs.github.com/en/billing/how-tos/products/view-productlicense-use)
