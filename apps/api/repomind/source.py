"""GitHub URL validation, source filtering, and deterministic chunking."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlsplit


ALLOWED_SUFFIXES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".go": "Go", ".rs": "Rust", ".c": "C", ".h": "C",
    ".cpp": "C++", ".hpp": "C++", ".cs": "C#", ".sql": "SQL",
    ".r": "R", ".html": "HTML", ".css": "CSS", ".json": "JSON",
    ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".xml": "XML",
    ".md": "Markdown", ".mdx": "Markdown", ".txt": "Text",
    ".sh": "Shell", ".bash": "Shell", ".ps1": "PowerShell",
}
EXCLUDED_PARTS = {
    ".git", ".next", ".venv", "venv", "node_modules", "dist", "build",
    "coverage", "__pycache__", ".pytest_cache", "target", "vendor",
}
EXCLUDED_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "uv.lock", "cargo.lock", "go.sum", "composer.lock",
}
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
REF_RE = re.compile(r"^[A-Za-z0-9_./-]{1,255}$")


def parse_repo_url(url: str) -> tuple[str, str]:
    parsed = urlsplit(url.strip())
    if (parsed.scheme != "https" or parsed.netloc.lower() != "github.com"
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError("Enter an https://github.com/owner/repository URL.")
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2:
        raise ValueError("Enter a repository URL without a file or branch path.")
    owner, name = parts
    name = name.removesuffix(".git")
    if not NAME_RE.fullmatch(owner) or not NAME_RE.fullmatch(name) or owner in {".", ".."} or name in {".", ".."}:
        raise ValueError("The GitHub owner or repository name is invalid.")
    return owner, name


def validate_ref(ref: str) -> str:
    if (not REF_RE.fullmatch(ref) or ref.startswith(("/", "-", "."))
            or ".." in ref or "//" in ref or ref.endswith(("/", "."))):
        raise ValueError("The branch or ref is invalid.")
    return ref


def supported_file(path: str, size: int, max_bytes: int) -> str | None:
    pure = PurePosixPath(path)
    if (not path or path.startswith("/") or "\\" in path or ".." in pure.parts
            or any(part.lower() in EXCLUDED_PARTS for part in pure.parts)
            or pure.name.lower() in EXCLUDED_NAMES or pure.name.endswith(".min.js")
            or size > max_bytes or size < 0):
        return None
    if pure.name.lower() in {"dockerfile", "makefile"}:
        return "Dockerfile" if pure.name.lower() == "dockerfile" else "Makefile"
    return ALLOWED_SUFFIXES.get(pure.suffix.lower())


def normalized_text(raw: bytes) -> str | None:
    if b"\x00" in raw:
        return None
    try:
        value = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    return value.replace("\r\n", "\n").replace("\r", "\n")


def fingerprint(*values: str) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(value.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


@dataclass(frozen=True)
class TextChunk:
    index: int
    start_line: int
    end_line: int
    content: str
    content_hash: str


def _sections(lines: list[str], language: str) -> list[tuple[int, int]]:
    if language != "Markdown":
        return [(0, len(lines))]
    starts = [0] + [i for i, line in enumerate(lines) if i and re.match(r"^#{1,6}\s", line)]
    return [(a, b) for a, b in zip(starts, starts[1:] + [len(lines)]) if a < b]


def chunk_text(path: str, content: str, language: str, target: int = 80,
               overlap: int = 12) -> list[TextChunk]:
    if target < 1 or overlap < 0 or overlap >= target:
        raise ValueError("Chunk target must exceed overlap and be positive.")
    lines = content.splitlines()
    if not lines:
        return []
    chunks: list[TextChunk] = []
    for section_start, section_end in _sections(lines, language):
        position = section_start
        while position < section_end:
            end = min(position + target, section_end)
            segment = "\n".join(lines[position:end]).strip("\n")
            if segment.strip():
                start_line, end_line = position + 1, end
                chunks.append(TextChunk(
                    index=len(chunks), start_line=start_line, end_line=end_line,
                    content=segment,
                    content_hash=fingerprint("v1", path, str(start_line), str(end_line), segment),
                ))
            if end == section_end:
                break
            position = end - overlap
    return chunks
