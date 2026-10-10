# Configuration: rates

Default USD per minute are GitHub's list prices from the
[Actions runner pricing reference](https://docs.github.com/en/billing/reference/actions-runner-pricing)
(checked 2026-10-10). `runbill rates` prints the full table.

## Standard runners

| SKU | GitHub billing SKU | $/min | Matched by labels |
|---|---|---:|---|
| `linux` | `actions_linux` | 0.006 | `ubuntu-*`, anything not matched below |
| `linux-slim` | `actions_linux_slim` | 0.002 | `ubuntu-slim` (1-core) |
| `linux-arm` | `actions_linux_arm` | 0.005 | `ubuntu-*-arm` |
| `windows` | `actions_windows` | 0.010 | `windows-*` |
| `windows-arm` | `actions_windows_arm` | 0.010 | `windows-*-arm` |
| `macos` | `actions_macos` | 0.062 | `macos-*` |
| `self-hosted` | | 0.000 | `self-hosted`, or a custom runner group |

## Larger runners

Larger runners have their own per-minute rate (not a multiple of more minutes). runbill reads the size from
the label:

- a core count such as `ubuntu-latest-8-cores`, `linux_16_core`, `windows-latest-4-cores`, `ubuntu-24.04-arm-8-core`
  maps to `linux-8-core`, `linux-16-core`, `windows-4-core`, `linux-arm-8-core` and so on
  (x64 Linux 4–96 cores, Windows 4–96, arm64 Linux 4–64, arm64 Windows 2–64)
- `macos-*-large` → `macos-large` ($0.077, 12-core Intel), `macos-*-xlarge` / `xcode-*-xlarge` → `macos-xlarge`
  ($0.102, M2 Pro)
- a label containing `gpu` → `linux-gpu` ($0.052) or `windows-gpu` ($0.102)
- 2-core x64 larger runners cost the same as standard ones and are billed as `linux` / `windows`

Larger-runner labels are chosen by your org admins, so name them with the core count for runbill to price them.
A core count with no published row (for example `12-cores`) falls back to the base rate × `cores / 2`.

## Overriding

```bash
runbill OWNER/REPO --rate macos=0.08 --rate linux-8-core=0.02 --rate self-hosted=0.002
```
