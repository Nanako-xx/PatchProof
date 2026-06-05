from __future__ import annotations

import re

from patchproof.core.state import TracebackFrame, TracebackSummary


_FRAME_RE = re.compile(r'File "([^"]+)", line (\d+)(?:, in ([^\s]+))?')
_EXCEPTION_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*Error|Exception):")


class TracebackParser:
    def parse(self, text: str) -> TracebackSummary:
        frames = [
            TracebackFrame(
                file_path=match.group(1),
                line_number=int(match.group(2)),
                function_name=match.group(3),
            )
            for match in _FRAME_RE.finditer(text)
        ]
        exception_match = _EXCEPTION_RE.search(text)
        return TracebackSummary(
            exception_type=exception_match.group(1) if exception_match else None,
            frames=frames,
        )
