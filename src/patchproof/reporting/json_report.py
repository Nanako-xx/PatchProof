from __future__ import annotations

import json
from pathlib import Path

from patchproof.core.state import RunState
from patchproof.llm.base import LLMCallTrace


def write_json_report(state: RunState, path: Path) -> None:
    payload = state.model_dump(mode="json")
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_llm_trace(call_trace: list[LLMCallTrace], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "llm_call_count": sum(trace.call_count for trace in call_trace),
        "llm_call_trace": [trace.model_dump(mode="json") for trace in call_trace],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
