from patchproof.tools.traceback_parser import TracebackParser


def test_traceback_parser_extracts_frames_and_exception():
    text = '''
E       AssertionError: assert -1 == 5
        File "test_calculator.py", line 4, in test_add
        File "calculator.py", line 2, in add
'''

    summary = TracebackParser().parse(text)

    assert summary.exception_type == "AssertionError"
    assert summary.frames[0].file_path == "test_calculator.py"
    assert summary.frames[0].line_number == 4
    assert summary.frames[0].function_name == "test_add"
    assert summary.frames[1].file_path == "calculator.py"


def test_traceback_parser_returns_empty_summary_for_non_traceback_text():
    summary = TracebackParser().parse("all good")

    assert summary.exception_type is None
    assert summary.frames == []
