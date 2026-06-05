from __future__ import annotations

import json
from pathlib import Path

from patchproof.core.state import RunState


def write_json_report(state: RunState, path: Path) -> None:
    payload = state.model_dump(mode="json")
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
