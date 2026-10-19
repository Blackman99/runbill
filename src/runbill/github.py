"""Tiny GitHub REST client (stdlib only)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Iterator, List, Optional

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")


class GitHubError(RuntimeError):
    pass


RETRY_STATUS = (500, 502, 503, 504)
MAX_RETRIES = 3  # attempts = 1 + MAX_RETRIES
BACKOFF = 1.0  # seconds; doubles each retry
MAX_WAIT = 60.0  # never sleep longer than this for one retry


def _retry_after(e: urllib.error.HTTPError, body: str) -> Optional[float]:
    """Seconds to wait before retrying, or None if this error is not transient."""
    ra = e.headers.get("Retry-After") if e.headers else None
    if ra:
        try:
            return max(0.0, float(ra))
        except ValueError:
            pass
    if e.code in RETRY_STATUS:
        return 0.0  # caller applies exponential backoff
    if e.code in (403, 429) and "secondary rate limit" in body.lower():
        return 0.0
    return None


def find_token() -> Optional[str]:
    for var in ("RUNBILL_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    if shutil.which("gh"):
        try:
            out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return None


class Client:
    def __init__(self, token: Optional[str] = None, api: str = API):
        self.token = token
        self.api = api.rstrip("/")
        self.calls = 0
        self._sleep = time.sleep

    def get(self, path: str, params: Optional[Dict[str, str]] = None) -> dict:
        url = path if path.startswith("http") else self.api + path
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "runbill",
            **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
        })
        self.calls += 1
        attempt = 0
        while True:
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", "replace")[:300]
                wait = _retry_after(e, body) if e.code >= 500 or e.code in (403, 429) else None
                if wait is not None and attempt < MAX_RETRIES:
                    self._sleep(min(MAX_WAIT, max(wait, BACKOFF * 2 ** attempt)))
                    attempt += 1
                    continue
                hint = ""
                if e.code in (401, 403) and not self.token:
                    hint = " (no token found: set GH_TOKEN or run `gh auth login`)"
                elif e.code in (403, 429) and "rate limit" in body.lower():
                    hint = " (rate limited: use a token, or narrow --days / --max-runs)"
                elif attempt:
                    hint = f" (after {attempt} retries)"
                raise GitHubError(f"GET {url} -> HTTP {e.code}{hint}: {body}") from None
            except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
                if attempt < MAX_RETRIES:
                    self._sleep(min(MAX_WAIT, BACKOFF * 2 ** attempt))
                    attempt += 1
                    continue
                reason = getattr(e, "reason", e)
                raise GitHubError(f"GET {url} failed after {attempt} retries: {reason}") from None

    def repo(self, repo: str) -> dict:
        return self.get(f"/repos/{repo}")

    def runs(self, repo: str, since: str, max_runs: int, workflow: Optional[str] = None,
             branch: Optional[str] = None) -> Iterator[dict]:
        base = f"/repos/{repo}/actions/workflows/{workflow}/runs" if workflow else f"/repos/{repo}/actions/runs"
        params = {"per_page": "100", "created": f">={since}"}
        if branch:
            params["branch"] = branch
        page, seen = 1, 0
        while seen < max_runs:
            data = self.get(base, {**params, "page": str(page)})
            batch = data.get("workflow_runs", [])
            if not batch:
                return
            for r in batch:
                if r.get("status") != "completed":
                    continue
                yield r
                seen += 1
                if seen >= max_runs:
                    return
            if len(batch) < 100:
                return
            page += 1

    def jobs(self, repo: str, run_id: int) -> List[dict]:
        out: List[dict] = []
        page = 1
        while True:
            data = self.get(f"/repos/{repo}/actions/runs/{run_id}/jobs",
                            {"filter": "all", "per_page": "100", "page": str(page)})
            batch = data.get("jobs", [])
            out.extend(batch)
            if len(batch) < 100:
                return out
            page += 1

    def list_repos(self, owner: str, include_archived: bool = False) -> List[dict]:
        """List repos for an org or user. Tries /orgs/ first, then /users/."""
        params = {"per_page": "100", "type": "all", "sort": "full_name"}
        for kind in ("orgs", "users"):
            out: List[dict] = []
            page = 1
            try:
                while True:
                    data = self.get(f"/{kind}/{owner}/repos", {**params, "page": str(page)})
                    if not isinstance(data, list):
                        break
                    for r in data:
                        if r.get("archived") and not include_archived:
                            continue
                        if r.get("disabled"):
                            continue
                        out.append(r)
                    if len(data) < 100:
                        return out
                    page += 1
            except GitHubError as e:
                if "HTTP 404" in str(e):
                    continue
                raise
        raise GitHubError(f"no such org or user: {owner}")
