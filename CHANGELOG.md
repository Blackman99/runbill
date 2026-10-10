# Changelog

## Unreleased

## v0.1.1 (2026-10-10)
- Landing page loads faster: static font instances and the hero scene is built after first paint (#6).
- New visual identity: isometric brick-city landing page, cube-stack logo, OG image, social preview and docs theme; Marketplace branding `box` / `blue`.
- Larger runners are priced at GitHub's published per-size rates (Linux/Windows x64 and arm64 by core count, macOS `large`/`xlarge`, GPU) instead of `cores/2 ×` the 2-core rate; billed minutes are no longer inflated by a size multiplier. 1-core `ubuntu-slim` detected at $0.002/min. Source: https://docs.github.com/en/billing/reference/actions-runner-pricing

## v0.1.0 (2026-10-10)
- First release: per-workflow/per-job billed minutes and cost, runner tariffs, re-run share, md/json/csv, budget gate, GitHub Action.
