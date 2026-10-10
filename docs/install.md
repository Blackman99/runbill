# Install

runbill needs Python 3.9 or newer and nothing else.

```bash
pipx install git+https://github.com/Blackman99/runbill
# or
pip install git+https://github.com/Blackman99/runbill
# or a pinned release wheel
pip install https://github.com/Blackman99/runbill/releases/download/v0.1.1/runbill-0.1.1-py3-none-any.whl
```

Check it: `runbill --version` and `runbill demo` (offline sample).

## Token

runbill looks for a token in this order: `RUNBILL_TOKEN`, `GH_TOKEN`, `GITHUB_TOKEN`, then `gh auth token`.
It only needs read access to Actions (`actions:read`; classic PATs need `repo` for private repos).
Public repos work without a token, but the anonymous rate limit (60 requests/hour) only covers a few dozen runs.
