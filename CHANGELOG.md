# Changelog

## Unreleased
- GitHub API calls now retry transient failures (HTTP 500/502/503/504, secondary rate limits, connection resets and timeouts, including read timeouts on Python 3.9) up to 3 times with exponential backoff (1s, 2s, 4s), honouring `Retry-After` (capped at 60s). Other 4xx errors still fail immediately.

## v0.3.0 (2026-10-19)
- `--by branch` / `--by event` (or `--by branch,event`): break billed minutes and cost down by head branch and by trigger event (push, pull_request, schedule, workflow_dispatch, merge_group, …), ranked by cost. Same per-job round-up as everything else, so each table adds up to the total. Branches past `--top` fold into one `N other branches` row in text/Markdown; JSON (`branches`, `events`) and CSV (`level` `branch` / `event`) list them all. Fork PRs show as `owner:branch`; runs with no branch or event are kept under `(no branch)` / `(unknown event)`. Works in `runbill org` too (branches as `repo › branch`), in `runbill demo`, and as the Action's new `by` input.
- Text table headers now line up with their columns; long names are cut with `…` (branch names keep their tail).
- `--top` must be 1 or more (was silently accepted as 0 or negative).

## v0.2.0 (2026-10-12)
- `runbill org ORG`: roll up Actions cost across every repo of an org or user, ranked by cost (respects `--days` / `--since` / `--max-runs` per repo / `--top` / `--rate` / `--format` / `--fail-over`; skips archived repos by default).

## v0.1.1 (2026-10-10)
- Landing page loads faster: static font instances and the hero scene is built after first paint (#6).
- New visual identity: isometric brick-city landing page, cube-stack logo, OG image, social preview and docs theme; Marketplace branding `box` / `blue`.
- Larger runners are priced at GitHub's published per-size rates (Linux/Windows x64 and arm64 by core count, macOS `large`/`xlarge`, GPU) instead of `cores/2 ×` the 2-core rate; billed minutes are no longer inflated by a size multiplier. 1-core `ubuntu-slim` detected at $0.002/min. Source: https://docs.github.com/en/billing/reference/actions-runner-pricing

## v0.1.0 (2026-10-10)
- First release: per-workflow/per-job billed minutes and cost, runner tariffs, re-run share, md/json/csv, budget gate, GitHub Action.
