# FAQ

**Why not the billing usage report?**
It's a CSV you download by hand from the billing page (workflow path is in it, for a limited window). runbill works from the API, per repo, in a terminal or a scheduled job, and adds the job-level and re-run view.

**Why not `/actions/workflows/{id}/timing`?**
GitHub has been closing that endpoint down for accounts on the new billing platform, and it never returned job-level detail or anything on public repos.

**Does it match my invoice?**
Not exactly. It doesn't know your included free minutes, discounts or contract prices. It's for finding where minutes go.

**Is my private repo data sent anywhere?**
No. runbill only talks to `api.github.com` (or `GITHUB_API_URL` for GHES) with your token.

**GitHub Enterprise Server?**
Set `GITHUB_API_URL=https://ghe.example.com/api/v3`.

**Why are some jobs $0?**
Self-hosted runners default to $0. Set `--rate self-hosted=...` if you want to price them.

**It stopped early.**
`--max-runs` caps API usage (default 500). Raise it, or narrow with `--days`, `--workflow` or `--branch`.
