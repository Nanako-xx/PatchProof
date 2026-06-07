from __future__ import annotations

from pathlib import Path

from patchproof.core.state import RunState


def render_markdown_report(state: RunState) -> str:
    lines = [
        "# PatchProof Report",
        "",
        f"- Project: `{state.project_path}`",
        f"- Test command: `{' '.join(state.test_command)}`",
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
