"""Findings model + rendering."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field


@dataclass
class Finding:
    layer: str          # "text" | "file"
    kind: str           # short machine slug, e.g. "zero-width"
    detail: str         # human description
    count: int = 1
    target: str = "-"   # path or "<stdin>"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, *args, **kwargs) -> None:
        self.findings.append(Finding(*args, **kwargs))

    def extend(self, others: list[Finding], target: str | None = None) -> None:
        for f in others:
            if target:
                f.target = target
            self.findings.append(f)

    def __bool__(self) -> bool:
        return bool(self.findings)

    def to_json(self) -> str:
        return json.dumps([asdict(f) for f in self.findings], indent=2)

    def to_text(self) -> str:
        if not self.findings:
            return "no provenance markers found"
        lines = []
        for f in self.findings:
            n = f" x{f.count}" if f.count > 1 else ""
            lines.append(f"  [{f.layer}] {f.target}: {f.detail}{n}")
        return "\n".join(lines)
