# runbill

GitHub's billing page tells you the **total** Actions minutes for the month. It doesn't tell you **which workflow or job** used them, and the per-workflow `timing` API that used to do that has been [closing down](https://github.blog/changelog/2025-02-02-actions-get-workflow-usage-and-get-workflow-run-usage-endpoints-closing-down/) since early 2025.

runbill rebuilds that breakdown from the ordinary runs and jobs API:

- billed minutes and estimated cost **per workflow** and **per job**
- each job **rounded up to the whole minute**, the way GitHub bills
- runner tariff from labels at GitHub's published rates: Linux, Windows, macOS, arm64, 1-core `ubuntu-slim`, larger runners (`N-cores`, macOS `large`/`xlarge`, GPU), self-hosted
- **re-run share**: how much of the bill came from retrying failed attempts
- text, Markdown (job summary), JSON and CSV output; optional `--fail-over` budget gate
- org-wide rollup: `runbill org ORG` ranks every repo by cost
- no dependencies, Python 3.9+, uses `GH_TOKEN` or your `gh` login

```console
$ runbill your-org/app --days 30
```

Start with [Install](install.md), then [Usage](usage.md). Running it in CI: [GitHub Action](action.md).

!!! note "It's an estimate"
    runbill multiplies whole minutes by list prices. Your invoice can differ: included free minutes,
    discounts, enterprise contracts. Use it to find *where* the minutes go, not to reconcile an invoice.
