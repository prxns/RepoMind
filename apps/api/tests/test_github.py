import base64

import httpx
import pytest

from repomind.config import Settings
from repomind.github import GithubClient, GithubError


def test_tree_and_blob_use_git_sha_endpoints():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path.endswith("/commits/main"):
            return httpx.Response(200, json={"sha": "a" * 40, "commit": {"tree": {"sha": "b" * 40}}})
        if "/git/trees/" in request.url.path:
            return httpx.Response(200, json={"truncated": False, "tree": [
                {"type": "blob", "path": "src/a.py", "sha": "c" * 40, "size": 12},
                {"type": "tree", "path": "src", "sha": "d" * 40},
            ]})
        return httpx.Response(200, json={"encoding": "base64", "content": base64.b64encode(b"print('ok')").decode()})

    http = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    client = GithubClient(Settings(), http)
    commit, files = client.snapshot_tree("o", "r", "main")
    assert commit == "a" * 40
    assert len(files) == 1 and files[0].path == "src/a.py"
    assert client.blob("o", "r", files[0].sha) == b"print('ok')"
    assert paths == ["/repos/o/r/commits/main", "/repos/o/r/git/trees/" + "b" * 40,
                     "/repos/o/r/git/blobs/" + "c" * 40]


def test_truncated_tree_is_rejected():
    def handler(request):
        if "/commits/" in request.url.path:
            return httpx.Response(200, json={"sha": "a", "commit": {"tree": {"sha": "b"}}})
        return httpx.Response(200, json={"truncated": True, "tree": []})

    http = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    with pytest.raises(GithubError) as exc:
        GithubClient(Settings(), http).snapshot_tree("o", "r", "main")
    assert exc.value.code == "TREE_TRUNCATED"
