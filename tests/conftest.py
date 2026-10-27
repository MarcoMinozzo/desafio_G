from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.tools.web_search import FakeWebSearch

ROOT = Path(__file__).resolve().parents[1]


def offline_settings() -> Settings:
    base = Settings.from_env()
    return Settings(
        openai_api_key="",
        openai_base_url="",
        openai_model=base.openai_model,
        corpus_dir=base.corpus_dir,
        merchants_path=base.merchants_path,
        chroma_dir=base.chroma_dir,
    )


@pytest.fixture
def client() -> TestClient:
    application = create_app(settings=offline_settings(), web_search=FakeWebSearch())
    return TestClient(application)


@pytest.fixture
def scenarios() -> list[dict]:
    payload = yaml.safe_load((ROOT / "data" / "evaluation.yaml").read_text(encoding="utf-8"))
    return payload["scenarios"]
