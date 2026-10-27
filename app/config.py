"""Runtime settings. An empty API key selects the offline path."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    corpus_dir: Path
    merchants_path: Path
    chroma_dir: Path
    ingest_on_start: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "").strip(),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            corpus_dir=ROOT / "data" / "corpus",
            merchants_path=ROOT / "data" / "merchants.json",
            chroma_dir=ROOT / "data" / ".chroma",
            ingest_on_start=os.getenv("GETNET_INGEST", "1").strip() != "0",
        )
