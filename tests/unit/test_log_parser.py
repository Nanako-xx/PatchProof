from patchproof.tools.log_parser import LogParser


def test_log_parser_extracts_level_file_line_and_message():
    text = "2026-06-08 ERROR src/app.py:42 ValueError: invalid user id"

    signals = LogParser().parse(text)

    assert len(signals) == 1
    assert signals[0].level == "ERROR"
    assert signals[0].file_path == "src/app.py"
    assert signals[0].line_number == 42
    assert "invalid user id" in signals[0].message


def test_log_parser_extracts_exception_line_without_file_hint():
    text = "ValueError: invalid user id"

    signals = LogParser().parse(text)

    assert len(signals) == 1
    assert signals[0].level is None
    assert signals[0].file_path is None
    assert signals[0].message == "ValueError: invalid user id"
