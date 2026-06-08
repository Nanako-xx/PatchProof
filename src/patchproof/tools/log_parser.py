from __future__ import annotations

import re

from patchproof.core.state import LogSignal


_LEVEL_RE = re.compile(r"\b(ERROR|WARNING|WARN|CRITICAL|FATAL)\b")
_FILE_LINE_RE = re.compile(r"\b([\w./\\-]+\.py):(\d+)\b")
_EXCEPTION_LINE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception):\s+.+)")


class LogParser:
    def parse(self, text: str) -> list[LogSignal]:
        signals: list[LogSignal] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            level_match = _LEVEL_RE.search(stripped)
            file_match = _FILE_LINE_RE.search(stripped)
            exception_match = _EXCEPTION_LINE_RE.search(stripped)
            if not (level_match or file_match or exception_match):
                continue

            signals.append(
                LogSignal.model_construct(
                    level=level_match.group(1) if level_match else None,
                    file_path=file_match.group(1) if file_match else None,
                    line_number=int(file_match.group(2)) if file_match else None,
                    message=exception_match.group(1) if exception_match else stripped,
                )
            )
        return signals
