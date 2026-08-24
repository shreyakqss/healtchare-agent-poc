from __future__ import annotations

import uuid
from typing import Any

from agno.workflow.types import StepInput


def case_id_from(step_input: StepInput) -> uuid.UUID:
    raw: Any = step_input.input
    if isinstance(raw, dict):
        return uuid.UUID(str(raw["case_id"]))
    return uuid.UUID(str(raw))