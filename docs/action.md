# GitHub Action

Writes the report to the job summary and exposes the JSON path as an output.

```yaml
name: Actions bill
on:
  schedule: [{cron: "0 6 * * 1"}]   # every Monday
  workflow_dispatch:
permissions:
  actions: read
  contents: read
jobs:
  meter:
    runs-on: ubuntu-latest
    steps:
      - id: bill
        uses: Blackman99/runbill@v0.4.0
        with:
          days: 7
          fail-over: 20   # optional: fail if the week's estimate is over $20
      - run: cat "${{ steps.bill.outputs.report }}"
```

| Input | Default | Meaning |
|---|---|---|
| `repo` | this repo | `OWNER/REPO` to meter |
| `days` | `30` | look-back window |
| `workflow` | all | only this workflow file |
| `top` | `10` | rows per table |
| `by` | none | add breakdowns: `branch`, `event`, or `branch,event` |
| `max-runs` | `500` | cap on runs fetched |
| `fail-over` | none | fail the step above this USD estimate |
| `compare` | `false` | `true`: compare the window with the one right before it (week over week with `days: 7`) |
| `fail-increase` | none | fail the step if cost rose more than this percent; turns on `compare` |
| `token` | `github.token` | needs `actions:read` |

Output `report`: path to the JSON report (with `branches` / `events` arrays when `by` is set; the
comparison shape from the [reference](reference.md#json-shape) when `compare` is on).

Week over week, posted every Monday, failing when the bill jumps by more than a quarter:

```yaml
      - uses: Blackman99/runbill@v0.4.0
        with:
          days: 7
          compare: true
          fail-increase: 25
```
