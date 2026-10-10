# Contributing

Thanks! Please read [GOAL.md](GOAL.md) first; PRs outside it will be closed politely.

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/runbill demo
```

- Keep runtime dependencies at zero (stdlib only).
- Billing logic lives in `src/runbill/core.py` as pure functions; add a test for every rule.
- If you change rates or labels matching, cite GitHub's docs in the PR.
- Landing page: `site/` (see `site/DESIGN.md`); docs: `docs/` (MkDocs Material).
