"""Onboarding endpoints: trigger a workflow, list/inspect runs, retry a step."""

from collections.abc import Iterator
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from onboarding.config import get_settings
from onboarding.database import session_scope
from onboarding.models import Employee, OnboardingRun, RunStatus, StepStatus
from onboarding.workflow import STEP_SEQUENCE, build_clients, get_run, retry_step, start_run

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def db_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session


# --- Schemas -----------------------------------------------------------------

class NewHire(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=200)
    start_date: date
    slack_handle: str | None = Field(default=None, max_length=100)
    manager_name: str | None = Field(default=None, max_length=200)


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_name: str
    status: StepStatus
    attempts: int
    error_message: str | None
    artifact_path: str | None
    completed_at: datetime | None


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: str
    email: str
    start_date: date
    slack_handle: str | None
    manager_name: str | None


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    overall_status: RunStatus
    triggered_at: datetime
    completed_at: datetime | None
    employee: EmployeeOut
    steps: list[StepOut]


# --- Endpoints ---------------------------------------------------------------

@router.post("/trigger", response_model=RunOut, status_code=201)
def trigger(payload: NewHire, session: Session = Depends(db_session)) -> OnboardingRun:
    settings = get_settings()
    employee = Employee(
        name=payload.name,
        role=payload.role,
        email=payload.email,
        start_date=payload.start_date,
        slack_handle=payload.slack_handle,
        manager_name=payload.manager_name,
    )
    session.add(employee)
    session.flush()
    return start_run(session, settings, employee, build_clients(settings))


@router.get("", response_model=list[RunOut])
def list_runs(session: Session = Depends(db_session)) -> list[OnboardingRun]:
    stmt = select(OnboardingRun).order_by(OnboardingRun.triggered_at.desc())
    return list(session.scalars(stmt))


@router.get("/{run_id}", response_model=RunOut)
def get_run_endpoint(run_id: int, session: Session = Depends(db_session)) -> OnboardingRun:
    run = get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@router.post("/{run_id}/retry/{step_name}", response_model=RunOut)
def retry(run_id: int, step_name: str, session: Session = Depends(db_session)) -> OnboardingRun:
    if step_name not in STEP_SEQUENCE:
        raise HTTPException(status_code=422, detail=f"unknown step {step_name!r}")
    run = get_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    step = next((s for s in run.steps if s.step_name == step_name), None)
    if step is None:
        raise HTTPException(status_code=404, detail="step not found on this run")
    if step.status == StepStatus.SUCCESS:
        raise HTTPException(status_code=409, detail="step already succeeded")
    settings = get_settings()
    retry_step(session, settings, run, step_name, build_clients(settings))
    return run
