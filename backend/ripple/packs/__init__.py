"""Region packs: one YAML per region, so thresholds change without code changes."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PACKS_DIR = Path(__file__).resolve().parent


def available_packs() -> list[str]:
    return sorted(p.stem for p in PACKS_DIR.glob("*.yaml"))


@lru_cache(maxsize=None)
def load_pack(pack_id: str) -> dict[str, Any]:
    path = PACKS_DIR / f"{pack_id}.yaml"
    if not path.is_file():
        raise KeyError(f"unknown pack: {pack_id}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)
