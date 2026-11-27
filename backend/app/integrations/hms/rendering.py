"""Plain-text rendering of structured payloads for chart documents. Staff read these notes, and
OpenEMR's upload guard declines content it sniffs as JSON ("insecure patient document"), so
payloads are rendered rather than serialised."""

from __future__ import annotations

from typing import Any


def _render_item(item: Any) -> str:
    if isinstance(item, dict):
        return ", ".join(f"{k}={v}" for k, v in item.items() if v not in (None, ""))
    return str(item)


def render_note(title: str, sections: dict[str, Any]) -> bytes:
    lines = [title, "=" * len(title), ""]
    for key, value in sections.items():
        label = key.replace("_", " ").capitalize()
        if isinstance(value, list):
            lines.append(f"{label}:")
            lines.extend(f"  - {_render_item(item)}" for item in value) if value else lines.append("  (none)")
        elif isinstance(value, dict):
            lines.append(f"{label}:")
            lines.extend(f"  {k}: {v}" for k, v in value.items())
        else:
            lines.append(f"{label}: {value if value not in (None, '') else '(none)'}")
    return "\n".join(lines).encode("utf-8")
