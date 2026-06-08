from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ParsedPytestResult:
    failed_tests: list[str] = field(default_factory=list)
    summary: str = ""


class PytestResultTool:
    def parse_junitxml(self, path: Path) -> ParsedPytestResult:
        root = ET.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
        failed_tests: list[str] = []
        totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}

        for suite in suites:
            for key in totals:
                totals[key] += int(suite.attrib.get(key, "0"))
            for testcase in suite.findall("testcase"):
                has_failure = testcase.find("failure") is not None
                has_error = testcase.find("error") is not None
                if not (has_failure or has_error):
                    continue
                file_name = testcase.attrib.get("file") or testcase.attrib.get("classname", "")
                test_name = testcase.attrib.get("name", "")
                failed_tests.append(f"{file_name}::{test_name}")

        summary = (
            f"{totals['tests']} tests, {totals['failures']} failures, "
            f"{totals['errors']} errors, {totals['skipped']} skipped"
        )
        return ParsedPytestResult(failed_tests=failed_tests, summary=summary)
