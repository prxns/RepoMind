from pathlib import Path

from scripts.check_secrets import scan_repository


ROOT = Path(__file__).resolve().parents[3]


def test_repository_has_no_obvious_committed_secrets():
    assert scan_repository(ROOT) == []


def test_environment_examples_keep_provider_secrets_empty():
    for name in (".env.example", ".env.production.example"):
        values = {}
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        assert values.get("GEMINI_API_KEY", "") == ""
        assert values.get("GITHUB_TOKEN", "") == ""
        assert not any(
            key.startswith("NEXT_PUBLIC_")
            and any(marker in key for marker in ("GEMINI", "GITHUB", "API_KEY", "TOKEN", "SECRET"))
            for key in values
        )
