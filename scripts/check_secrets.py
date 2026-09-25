"""Fail when source files contain common committed-secret patterns."""

import re
import subprocess
from pathlib import Path


SKIPPED_DIRECTORIES = {
    ".git", ".mypy_cache", ".next", ".pytest_cache", ".ruff_cache", ".venv",
    "__pycache__", "node_modules", "playwright-report", "test-results",
}
TEXT_SUFFIXES = {
    "", ".css", ".env", ".example", ".html", ".ini", ".js", ".json", ".jsonl", ".md",
    ".mjs", ".py", ".sh", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}
OBVIOUS_SECRET_PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "GitHub token": re.compile(r"gh[opurs]_[0-9A-Za-z]{36,255}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
SENSITIVE_ENV_NAMES = {
    "GEMINI_API_KEY", "GITHUB_TOKEN", "LLM_API_KEY", "BASIC_AUTH_HASH",
    "POSTGRES_PASSWORD",
}


def _candidate_files(root: Path):
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Without Git metadata, avoid inspecting the conventional private local env file.
        paths = (path for path in root.rglob("*") if path.name != ".env")
    else:
        paths = (root / name for name in result.stdout.split("\0") if name)

    for path in paths:
        if not path.is_file() or any(part in SKIPPED_DIRECTORIES for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name.startswith(".env"):
            yield path


def scan_repository(root: Path) -> list[str]:
    findings: list[str] = []
    public_prefix = "NEXT_" + "PUBLIC_"
    for path in _candidate_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(root)
        for label, pattern in OBVIOUS_SECRET_PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{relative}:{line}: possible {label}")
        for line_number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, value = (part.strip() for part in stripped.split("=", 1))
            if name.startswith(public_prefix) and any(
                marker in name for marker in ("GEMINI", "GITHUB", "API_KEY", "TOKEN", "SECRET")
            ):
                findings.append(
                    f"{relative}:{line_number}: secret-like variable uses NEXT_PUBLIC_"
                )
            if path.name.startswith(".env") and name in SENSITIVE_ENV_NAMES and value:
                findings.append(f"{relative}:{line_number}: example secret must be empty")
    return findings


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = scan_repository(root)
    if findings:
        print("\n".join(findings))
        return 1
    print("Secret scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
