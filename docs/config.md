# Configuration: rates

Default USD per minute (list prices for GitHub-hosted standard runners; check
[GitHub's pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing) for current numbers):

| SKU | $/min | Matched by labels |
|---|---:|---|
| `linux` | 0.006 | `ubuntu-*`, anything not matched below |
| `linux-arm` | 0.005 | `ubuntu-*-arm` |
| `windows` | 0.010 | `windows-*` |
| `windows-arm` | 0.010 | `windows-*-arm` |
| `macos` | 0.062 | `macos-*` |
| `self-hosted` | 0.000 | `self-hosted`, or a custom runner group |

Larger runners named like `ubuntu-latest-8-cores` get a multiplier of `cores / 2` (so 8-core = 4× the 2-core rate).

Override any rate:

```bash
runbill OWNER/REPO --rate macos=0.08 --rate self-hosted=0.002
```

`runbill rates` prints the table.
