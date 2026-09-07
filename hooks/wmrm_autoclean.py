#!/usr/bin/env python3
"""PostToolUse hook: clean layer-A markers out of every file the agent writes.

Reads the hook payload on stdin, pulls `tool_input.file_path`, and runs an
in-place clean when the extension is in scope. Two scopes, on purpose:

  prose  (.md .txt .rst .html)  full clean - invisibles, smart punctuation,
                                homoglyphs. This is text meant to be read.
  code   (.py .js .ts .go ...)  invisibles only. Normalizing quotes or dashes
                                inside a source file rewrites string literals
                                and comments, which is a real behavior change.

Everything else is left alone. Never blocks: always exits 0, even on error -
a hook that breaks the session is worse than an uncleaned file.

Install: copy to ~/.claude/hooks/ and register as a PostToolUse hook matching
Write|Edit. See README.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROSE = {".md", ".markdown", ".txt", ".rst", ".html", ".htm"}
CODE = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".h",
    ".cpp", ".cs", ".rb", ".php", ".sh", ".ps1", ".sql", ".yml", ".yaml",
    ".toml", ".ini", ".css", ".scss",
}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    raw = (payload.get("tool_input") or {}).get("file_path")
    if not raw:
        return 0

    path = Path(raw)
    ext = path.suffix.lower()
    if ext in PROSE:
        extra: list[str] = []
    elif ext in CODE:
        extra = ["--keep-typography", "--keep-homoglyphs"]
    else:
        return 0

    if not path.is_file():
        return 0

    try:
        proc = subprocess.run(
            ["wmrm", "clean", str(path), "--in-place", "--force", "--json", *extra],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return 0  # wmrm not installed or wedged: stay out of the way

    # wmrm reports findings on stderr as JSON. Only speak up when it changed
    # something, so a clean write stays silent.
    try:
        findings = json.loads(proc.stderr or "[]")
    except (json.JSONDecodeError, ValueError):
        return 0
    if findings:
        summary = ", ".join(sorted({f["detail"] for f in findings}))
        print(f"wmrm: cleaned {path.name} ({summary})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
