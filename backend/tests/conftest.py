"""Put `backend/` on sys.path so the suite runs from the repo root too.

Backend imports are top-level absolute (`from config import settings`), which
works when pytest is invoked from `backend/` but not from the repo root. Three
lines here beats a confusing collection error.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
