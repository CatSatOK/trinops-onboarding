import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from onboarding.config import Settings
from onboarding.models import Base

REPO_ROOT = Path(__file__).resolve().parent.parent

# Jinja templates are loaded relative to the repo root
os.chdir(REPO_ROOT)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        demo_mode=True,
        demo_flaky_steps=[],  # deterministic by default; tests opt in explicitly
        pack_dir=str(tmp_path / "welcome_packs"),
        outbox_dir=str(tmp_path / "outbox"),
        calendar_dir=str(tmp_path / "calendar"),
        database_url=f"sqlite:///{tmp_path}/test.db",
    )


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
