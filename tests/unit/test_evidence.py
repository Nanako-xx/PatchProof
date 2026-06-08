from pathlib import Path

from patchproof.core.state import EvidenceSourceType, TestRunResult, TestRunStatus
from patchproof.tools.evidence import BugEvidenceBuilder, EvidenceInput, LogFileEvidenceReader, TextEvidenceReader


TRACEBACK_TEXT = '''
Traceback (most recent call last):
  File "tests/test_parser.py", line 6, in test_parse
    parse_count("x")
  File "src/parser.py", line 3, in parse_count
    return int(value)
ValueError: invalid literal for int() with base 10: 'x'
'''


def test_text_evidence_reader_returns_source():
    source = TextEvidenceReader().read("pasted traceback", TRACEBACK_TEXT)

    assert source.source_type == EvidenceSourceType.BUG_TEXT
    assert source.label == "pasted traceback"
    assert "ValueError" in source.raw_text


def test_log_file_evidence_reader_reads_utf8_file(tmp_path: Path):
    log_path = tmp_path / "error.log"
    log_path.write_text(TRACEBACK_TEXT, encoding="utf-8")

    source = LogFileEvidenceReader().read(log_path)

    assert source.source_type == EvidenceSourceType.BUG_LOG
    assert source.path == log_path
    assert "tests/test_parser.py" in source.raw_text


def test_bug_evidence_builder_merges_sources_and_classifies_files():
    source = TextEvidenceReader().read("pasted traceback", TRACEBACK_TEXT)

    evidence = BugEvidenceBuilder().build([source])

    assert evidence.traceback_summary.exception_type == "ValueError"
    assert evidence.entrypoint_files == ["tests/test_parser.py"]
    assert evidence.suspected_files == ["src/parser.py"]
    assert evidence.summary == "ValueError in src/parser.py"


def test_bug_evidence_builder_adds_test_output_source():
    result = TestRunResult(
        status=TestRunStatus.FAILED,
        command=["pytest", "-q"],
        exit_code=1,
        stdout=TRACEBACK_TEXT,
        stderr="",
        traceback_text=TRACEBACK_TEXT,
        summary="1 failed",
    )

    evidence = BugEvidenceBuilder().build([EvidenceInput.from_test_result(result)])

    assert evidence.sources[0].source_type == EvidenceSourceType.TEST_OUTPUT
    assert evidence.raw_text.count("ValueError") == 1
