from pathlib import Path

from patchproof.tools.pytest_result import PytestResultTool


def test_parse_junitxml_failed_test(tmp_path: Path):
    xml = tmp_path / "result.xml"
    xml.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="1" failures="1" errors="0" skipped="0">
  <testcase classname="test_calculator" name="test_add" file="test_calculator.py" line="3">
    <failure message="assert -1 == 5">AssertionError: assert -1 == 5</failure>
  </testcase>
</testsuite>
""",
        encoding="utf-8",
    )

    parsed = PytestResultTool().parse_junitxml(xml)

    assert parsed.failed_tests == ["test_calculator.py::test_add"]
    assert parsed.summary == "1 tests, 1 failures, 0 errors, 0 skipped"


def test_parse_junitxml_collects_errors_from_testsuites_root(tmp_path: Path):
    xml = tmp_path / "result.xml"
    xml.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="2" failures="0" errors="1" skipped="1">
    <testcase classname="tests.test_parser" name="test_parse">
      <error message="ValueError">ValueError: bad input</error>
    </testcase>
    <testcase classname="tests.test_parser" name="test_skip">
      <skipped />
    </testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )

    parsed = PytestResultTool().parse_junitxml(xml)

    assert parsed.failed_tests == ["tests.test_parser::test_parse"]
    assert parsed.summary == "2 tests, 0 failures, 1 errors, 1 skipped"
