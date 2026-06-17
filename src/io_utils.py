"""Small shared I/O helpers (JSON loading) used across layers."""
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)