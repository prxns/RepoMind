"""Bounded GitHub REST client for public repository snapshots."""

import base64
import time
from dataclasses import dataclass
from urllib.parse import quote

import httpx

from repomind.config import Settings
from repomind.source import validate_ref


class GithubError(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class TreeFile:
    path: str
    sha: str
    size: int


class GithubClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self.client = client or httpx.Client(
            base_url=settings.github_api_url.rstrip("/"), timeout=20,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "RepoMind/0.1",
                **({"Authorization": f"Bearer {settings.github_token}"} if settings.github_token else {}),
            },
        )

    def _get(self, path: str) -> dict:
        for attempt in range(4):
            try:
                response = self.client.get(path)
            except httpx.RequestError as exc:
                if attempt == 3:
                    raise GithubError("GITHUB_UNAVAILABLE", "GitHub is unavailable.", True) from exc
                time.sleep(min(2 ** attempt, 8))
                continue
            if response.status_code == 404:
                raise GithubError("REPOSITORY_NOT_FOUND", "Repository or ref was not found.")
            limited = response.status_code == 429 or (
                response.status_code == 403 and (
                    response.headers.get("x-ratelimit-remaining") == "0"
                    or "Retry-After" in response.headers
                    or "secondary rate limit" in response.text.lower()
                )
            )
            if limited or response.status_code in {500, 502, 503, 504}:
                if attempt == 3:
                    raise GithubError("GITHUB_RATE_LIMITED" if limited else "GITHUB_UNAVAILABLE",
                                      "GitHub could not complete the request.", True)
                try:
                    delay = float(response.headers.get("Retry-After", ""))
                except ValueError:
                    delay = 2 ** attempt
                time.sleep(min(max(delay, 0), 30))
                continue
            if response.status_code >= 400:
                raise GithubError("GITHUB_ERROR", "GitHub rejected the request.")
            return response.json()
        raise GithubError("GITHUB_UNAVAILABLE", "GitHub is unavailable.", True)

    def repository(self, owner: str, name: str) -> dict:
        data = self._get(f"/repos/{owner}/{name}")
        if data.get("private"):
            raise GithubError("PRIVATE_REPOSITORY", "Only public repositories are supported.")
        return data

    def snapshot_tree(self, owner: str, name: str, ref: str) -> tuple[str, list[TreeFile]]:
        ref = validate_ref(ref)
        commit = self._get(f"/repos/{owner}/{name}/commits/{quote(ref, safe='')}")
        commit_sha = commit["sha"]
        tree_sha = commit["commit"]["tree"]["sha"]
        tree = self._get(f"/repos/{owner}/{name}/git/trees/{tree_sha}?recursive=1")
        if tree.get("truncated"):
            raise GithubError("TREE_TRUNCATED", "Repository tree is too large to index safely.")
        files = [TreeFile(item["path"], item["sha"], item.get("size", 0))
                 for item in tree["tree"] if item["type"] == "blob"]
        return commit_sha, files

    def blob(self, owner: str, name: str, sha: str) -> bytes:
        data = self._get(f"/repos/{owner}/{name}/git/blobs/{sha}")
        if data.get("encoding") != "base64":
            raise GithubError("UNSUPPORTED_BLOB", "GitHub returned unsupported content.")
        try:
            return base64.b64decode(data["content"], validate=False)
        except (KeyError, ValueError) as exc:
            raise GithubError("INVALID_BLOB", "GitHub returned invalid content.") from exc
