"""SQLAlchemy 2.0 models for the onboarding workflow."""

import enum
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class StepStatus(enum.StrEnum):
    PENDING = "PENDING"      # queued, not yet attempted
    RUNNING = "RUNNING"      # in progress
    SUCCESS = "SUCCESS"      # completed cleanly
    FAILED = "FAILED"        # attempted and errored — retryable


class RunStatus(enum.StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"  # every step succeeded
    PARTIAL = "PARTIAL"      # some steps succeeded, some failed
    FAILED = "FAILED"        # every step failed


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date)
    slack_handle: Mapped[str | None] = mapped_column(String(100))
    manager_name: Mapped[str | None] = mapped_column(String(200))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    runs: Mapped[list["OnboardingRun"]] = relationship(back_populates="employee")

    @property
    def first_name(self) -> str:
        return self.name.split()[0] if self.name else ""

    def __repr__(self) -> str:
        return f"<Employee {self.id} {self.name!r} {self.role!r}>"


class OnboardingRun(Base):
    """One onboarding workflow execution for one new hire."""

    __tablename__ = "onboarding_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    overall_status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, native_enum=False, length=20),
        default=RunStatus.PENDING,
        index=True,
    )

    employee: Mapped[Employee] = relationship(back_populates="runs")
    steps: Mapped[list["OnboardingStep"]] = relationship(
        back_populates="run",
        order_by="OnboardingStep.id",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<OnboardingRun {self.id} emp={self.employee_id} {self.overall_status}>"


class OnboardingStep(Base):
    """One step within a run. Each is logged, retried and reported separately."""

    __tablename__ = "onboarding_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("onboarding_runs.id"), index=True)
    step_name: Mapped[str] = mapped_column(String(50))
    status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, native_enum=False, length=20),
        default=StepStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    artifact_path: Mapped[str | None] = mapped_column(String(500))  # PDF path, event ids, outbox file
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[OnboardingRun] = relationship(back_populates="steps")

    def __repr__(self) -> str:
        return f"<OnboardingStep {self.step_name} {self.status} attempts={self.attempts}>"
