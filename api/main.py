"""FastAPI app: onboarding API. The run tracker is a separate Streamlit app."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from onboarding.config import get_settings
from onboarding.database import init_db, session_scope
from onboarding.logging_conf import setup_logging
from onboarding.seed_loader import seed_and_run
from onboarding.workflow import build_clients
from api.routes.onboarding import router as onboarding_router
from api.auth import require_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    settings = get_settings()
    with session_scope() as session:
        seed_and_run(session, settings, build_clients(settings))
    yield


app = FastAPI(title="Trinops Onboarding", lifespan=lifespan)
app.include_router(onboarding_router, dependencies=[Depends(require_admin)])


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
