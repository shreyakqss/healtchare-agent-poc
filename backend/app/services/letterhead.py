"""Per-clinic letterhead image for the doctor's patient-facing report.

Not an OpenEMR concept - its Facility/Organization resource carries no image field - and not
clinical data, so it lives with this app's own clinic branding/config (alongside
data/hospitals/*.yaml) rather than in the hospital system. One image per hospital_id, stored
on disk next to the case-attachment uploads this app already manages.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.core.errors import Unprocessable

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}
MAX_SIZE_BYTES = 2 * 1024 * 1024


def _dir() -> Path:
    d = settings.UPLOAD_DIR / "hospital-letterheads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _existing(hospital_id: str) -> Path | None:
    for ext in ALLOWED_EXTENSIONS:
        candidate = _dir() / f"{hospital_id}{ext}"
        if candidate.exists():
            return candidate
    return None


def exists(hospital_id: str) -> bool:
    return _existing(hospital_id) is not None


def save(hospital_id: str, filename: str, content: bytes) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise Unprocessable(f"Unsupported image type {ext or '(none)'}. Use PNG or JPEG.")
    if len(content) > MAX_SIZE_BYTES:
        raise Unprocessable("Letterhead image must be under 2 MB.")
    existing = _existing(hospital_id)
    if existing and existing.suffix != ext:
        existing.unlink()
    (_dir() / f"{hospital_id}{ext}").write_bytes(content)


def path_for(hospital_id: str) -> Path:
    path = _existing(hospital_id)
    if path is None:
        raise FileNotFoundError(hospital_id)
    return path
