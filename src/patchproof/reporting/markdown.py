from __future__ import annotations

from pathlib import Path

from patchproof.core.state import RunState


def _format_command(command: list[str]) -> str:
    return " ".join(command) if command else "not provided"


def _format_values(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _append_bug_evidence(lines: list[str], state: RunState) -> None:
    evidence = state.bug_evidence
    if evidence is None:
        return

    lines.extend(
        [
            "",
            "## Bug Evidence",
            "",
            f"- Summary: {evidence.summary or 'none'}",
            f"- Suspected files: {_format_values(evidence.suspected_files)}",
            f"- Entrypoint files: {_format_values(evidence.entrypoint_files)}",
        ]
    )

    if evidence.sources:
        lines.extend(["", "### Sources", ""])
        for source in evidence.sources:
            label = f" ({source.label})" if source.label else ""
            lines.append(f"- {source.source_type.value}{label}")
            extracted_text = getattr(source, "extracted_text", "")
            if extracted_text:
                lines.extend(["", "Extracted text:", "", "```text", extracted_text, "```"])
            elif source.raw_text:
                lines.extend(["", "Raw text:", "", "```text", source.raw_text, "```"])

    if evidence.traceback_summary.frames:
        lines.extend(["", "### Parsed Frames", ""])
        for frame in evidence.traceback_summary.frames:
            location = f"{frame.file_path}:{frame.line_number}"
            function = f" in {frame.function_name}" if frame.function_name else ""
            lines.append(f"- {location}{function}")


def _append_verification_plan(lines: list[str], state: RunState) -> None:
    plan = state.verification_plan
    if plan is None:
        return

    lines.extend(["", "## Verification Plan", "", "Attempted candidates:"])
    if plan.commands:
        for command in plan.commands:
            lines.append(f"- `{_format_command(command.command)}` ({command.source.value}): {command.reason}")
    else:
        lines.append("- none")

    lines.extend(["", "Skipped candidates:"])
    if plan.skipped_commands:
        for command in plan.skipped_commands:
            lines.append(f"- Skipped `{_format_command(command.command)}` ({command.source.value}): {command.reason}")
    else:
        lines.append("- none")


def render_markdown_report(state: RunState) -> str:
    test_command = _format_command(state.test_command) if state.test_command else "not provided"
    lines = [
        "# PatchProof Report",
        "",
        f"- Project: `{state.project_path}`",
        f"- Test command: `{test_command}`",
        f"- Final status: `{state.final_status.value}`",
    ]
    if state.stop_reason:
        lines.append(f"- Stop reason: {state.stop_reason}")
    if state.baseline_test_result is not None:
        lines.extend(
            [
                "",
                "## Baseline",
                "",
                f"- Summary: {state.baseline_test_result.summary}",
                f"- Failed tests: {', '.join(state.baseline_test_result.failed_tests)}",
            ]
        )
    _append_bug_evidence(lines, state)
    if state.investigation is not None:
        lines.extend(
            [
                "",
                "## Investigation",
                "",
                f"- Suspected files: {', '.join(state.investigation.suspected_files)}",
                f"- Selected hypothesis: {state.investigation.selected_hypothesis.description}",
                f"- Evidence: {state.investigation.selected_hypothesis.evidence}",
            ]
        )
    _append_verification_plan(lines, state)
    if state.attempts:
        lines.extend(["", "## Attempts", ""])
        for index, attempt in enumerate(state.attempts, start=1):
            review_decision = attempt.review_decision.value if attempt.review_decision else "not_reviewed"
            lines.extend(
                [
                    f"### Attempt {index}",
                    "",
                    f"- Review: `{review_decision}`",
                    f"- Verification: `{attempt.verification_status.value}`",
                    f"- Explanation: {attempt.patch_explanation}",
                    f"- Review summary: {attempt.review_summary}",
                ]
            )
            if attempt.verification_command is not None:
                lines.append(f"- Verification command: `{_format_command(attempt.verification_command.command)}`")
            if attempt.patch_apply_error:
                lines.append(f"- Patch apply error: `{attempt.patch_apply_error.strip()}`")
            if attempt.verification_result is not None:
                lines.append(f"- Verification summary: {attempt.verification_result.summary}")
            lines.extend(
                [
                    "",
                    "```diff",
                    attempt.patch_diff,
                    "```",
                ]
            )
    if state.coach_explanation is not None:
        lines.extend(
            [
                "",
                "## Beginner Explanation",
                "",
                state.coach_explanation.bug_explanation,
            ]
        )
    return "\n".join(lines) + "\n"


def write_markdown_report(state: RunState, path: Path) -> None:
    path.write_text(render_markdown_report(state), encoding="utf-8")
