from __future__ import annotations

from pathlib import Path
from typing import Iterable

from patchproof.core.state import (
    BugEvidence,
    BugEvidenceSource,
    EvidenceSourceType,
    TestRunResult,
    TracebackFrame,
)
from patchproof.tools.log_parser import LogParser
from patchproof.tools.traceback_parser import TracebackParser


class EvidenceInput:
    @staticmethod
    def from_test_result(result: TestRunResult) -> BugEvidenceSource:
        raw_text = result.traceback_text or "\n".join(part for part in [result.stdout, result.stderr] if part)
        return BugEvidenceSource(
            source_type=EvidenceSourceType.TEST_OUTPUT,
            label=" ".join(result.command),
            raw_text=raw_text,
        )


class TextEvidenceReader:
    def read(self, label: str, text: str) -> BugEvidenceSource:
        return BugEvidenceSource(source_type=EvidenceSourceType.BUG_TEXT, label=label, raw_text=text)


class LogFileEvidenceReader:
    def read(self, path: Path) -> BugEvidenceSource:
        source = BugEvidenceSource(
            source_type=EvidenceSourceType.BUG_LOG,
            label=str(path),
            file_path=str(path),
            raw_text=path.read_text(encoding="utf-8"),
        )
        object.__setattr__(source, "path", path)
        return source


class BugEvidenceBuilder:
    def __init__(
        self,
        traceback_parser: TracebackParser | None = None,
        log_parser: LogParser | None = None,
    ) -> None:
        self._traceback_parser = traceback_parser or TracebackParser()
        self._log_parser = log_parser or LogParser()

    def build(self, sources: Iterable[BugEvidenceSource]) -> BugEvidence:
        source_list = list(sources)
        raw_text = "\n".join(source.raw_text for source in source_list if source.raw_text)
        traceback_summary = self._traceback_parser.parse(raw_text)
        log_signals = self._log_parser.parse(raw_text)
        entrypoint_files = _unique(
            frame.file_path for frame in traceback_summary.frames if _is_entrypoint_frame(frame)
        )
        suspected_files = _unique(
            frame.file_path
            for frame in traceback_summary.frames
            if frame.file_path.endswith(".py") and not _is_entrypoint_frame(frame)
        )
        if not suspected_files:
            suspected_files = _unique(signal.file_path for signal in log_signals if signal.file_path)

        return BugEvidence(
            sources=source_list,
            raw_text=raw_text,
            traceback_summary=traceback_summary,
            log_signals=log_signals,
            suspected_files=suspected_files,
            entrypoint_files=entrypoint_files,
            summary=_summarize(traceback_summary.exception_type, suspected_files),
        )


def _is_entrypoint_frame(frame: TracebackFrame) -> bool:
    path = frame.file_path.replace("\\", "/")
    filename = Path(path).name
    return path.startswith("tests/") or filename.startswith("test_") or filename.endswith("_test.py")


def _unique(values: Iterable[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _summarize(exception_type: str | None, suspected_files: list[str]) -> str:
    if exception_type and suspected_files:
        return f"{exception_type} in {suspected_files[-1]}"
    if exception_type:
        return exception_type
    if suspected_files:
        return f"Bug evidence points to {suspected_files[-1]}"
    return "Bug evidence collected without a parsed traceback."
