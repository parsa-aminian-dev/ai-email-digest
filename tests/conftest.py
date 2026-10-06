from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.digest.config.settings import Settings  # noqa: E402
from src.digest.service import DigestService  # noqa: E402


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        demo_mode=True,
        database_url=f"sqlite:///{tmp_path}/app.db",
        output_dir=str(tmp_path / "digests"),
        config_path=str(ROOT / "config/config.example.yaml"),
        rules_path=str(ROOT / "config/rules.example.yaml"),
    )


@pytest.fixture
def service(test_settings: Settings):
    current = DigestService(test_settings)
    yield current
    current.close()
