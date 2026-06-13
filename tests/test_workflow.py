"""Workflow tests: per-step logging, fault tolerance, retry, finalisation."""

from dataclasses import dataclass, field
from datetime import date

import pytest

from onboarding.calendar_events import build_onboarding_events
from onboarding.config import Settings
from onboarding.models import Employee, RunStatus, StepStatus
from onboarding.workflow import STEP_SEQUENCE, Clients, retry_step, start_run


# --- Fakes -------------------------------------------------------------------

@dataclass
class FakeNotifier:
    sent: list[dict] = field(default_factory=list)
    raises: bool = False

    def send(self, to, subject, html_body, attachment=None):
        if self.raises:
            raise RuntimeError("smtp down")
        self.sent.append({"to": to, "subject": subject})
        return f"fake-thread-{len(self.sent)}"


@dataclass
class FakeCalendar:
    created: list[str] = field(default_factory=list)

    def create_event(self, summary, start, end, description):
        eid = f"evt-{len(self.created) + 1}"
        self.created.append(summary)
        return eid


@dataclass
class FakeSlack:
    posted: list[str] = field(default_factory=list)
    raises: bool = False

    def post(self, channel, message):
        if self.raises:
            raise RuntimeError("slack 500")
        self.posted.append(message)
        return f"slack-{len(self.posted)}"


def _fake_pack(employee, settings):
    return f"/tmp/pack_{employee.id}.pdf"


def make_clients(**overrides) -> Clients:
    return Clients(
        notifier=overrides.get("notifier", FakeNotifier()),
        calendar=overrides.get("calendar", FakeCalendar()),
        slack=overrides.get("slack", FakeSlack()),
        pack_generator=overrides.get("pack_generator", _fake_pack),
    )


def _employee(session, **overrides) -> Employee:
    defaults = dict(
        name="Alex Example",
        role="Operations Analyst",
        email="alex.example@company-a.example.com",
        slack_handle="@alex.example",
        manager_name="Morgan Example",
        start_date=date(2026, 7, 1),
    )
    defaults.update(overrides)
    employee = Employee(**defaults)
    session.add(employee)
    session.flush()
    return employee


# --- Happy path --------------------------------------------------------------

class TestSuccessfulRun:
    def test_all_steps_succeed_and_run_completes(self, session, settings):
        clients = make_clients()
        employee = _employee(session)

        run = start_run(session, settings, employee, clients)

        assert run.overall_status == RunStatus.COMPLETED
        assert run.completed_at is not None
        assert [s.step_name for s in run.steps] == list(STEP_SEQUENCE)
        assert all(s.status == StepStatus.SUCCESS for s in run.steps)
        assert all(s.attempts == 1 for s in run.steps)

    def test_side_effects_fire_once(self, session, settings):
        notifier, calendar, slack = FakeNotifier(), FakeCalendar(), FakeSlack()
        clients = make_clients(notifier=notifier, calendar=calendar, slack=slack)
        employee = _employee(session)

        start_run(session, settings, employee, clients)

        assert len(notifier.sent) == 1
        assert len(calendar.created) == 3  # Day 1, team intro, probation review
        assert len(slack.posted) == 1

    def test_artifacts_recorded(self, session, settings):
        clients = make_clients()
        employee = _employee(session)
        run = start_run(session, settings, employee, clients)
        by_name = {s.step_name: s for s in run.steps}
        assert by_name["calendar_events"].artifact_path.count("evt-") == 3
        assert by_name["welcome_pack"].artifact_path.endswith(".pdf")


# --- Fault tolerance ---------------------------------------------------------

class TestFaultTolerance:
    def test_one_failure_is_isolated_and_run_is_partial(self, session, settings):
        clients = make_clients(slack=FakeSlack(raises=True))
        employee = _employee(session)

        run = start_run(session, settings, employee, clients)

        by_name = {s.step_name: s for s in run.steps}
        assert run.overall_status == RunStatus.PARTIAL
        assert by_name["slack_notification"].status == StepStatus.FAILED
        assert "slack 500" in by_name["slack_notification"].error_message
        # earlier steps still ran and succeeded
        assert by_name["welcome_email"].status == StepStatus.SUCCESS
        assert by_name["welcome_pack"].status == StepStatus.SUCCESS

    def test_all_failures_mark_run_failed(self, session, settings):
        clients = make_clients(
            notifier=FakeNotifier(raises=True),
            slack=FakeSlack(raises=True),
        )
        # also break calendar + pack
        clients.calendar.create_event = _raise  # type: ignore[assignment]
        clients.pack_generator = _raise_pack
        employee = _employee(session)

        run = start_run(session, settings, employee, clients)
        assert run.overall_status == RunStatus.FAILED
        assert all(s.status == StepStatus.FAILED for s in run.steps)


# --- Retry -------------------------------------------------------------------

class TestRetry:
    def test_failed_step_retried_to_success_promotes_run(self, session, settings):
        slack = FakeSlack(raises=True)
        clients = make_clients(slack=slack)
        employee = _employee(session)
        run = start_run(session, settings, employee, clients)
        assert run.overall_status == RunStatus.PARTIAL

        slack.raises = False  # the transient issue clears
        step = retry_step(session, settings, run, "slack_notification", clients)

        assert step.status == StepStatus.SUCCESS
        assert step.attempts == 2
        assert run.overall_status == RunStatus.COMPLETED

    def test_retry_unknown_step_raises(self, session, settings):
        clients = make_clients()
        employee = _employee(session)
        run = start_run(session, settings, employee, clients)
        with pytest.raises(KeyError):
            retry_step(session, settings, run, "nope", clients)


# --- Demo fault injection ----------------------------------------------------

class TestDemoFlakyStep:
    def test_flaky_step_fails_first_then_succeeds_on_retry(self, session, settings):
        settings.demo_flaky_steps = ["slack_notification"]
        clients = make_clients()
        employee = _employee(session)

        run = start_run(session, settings, employee, clients)
        slack_step = next(s for s in run.steps if s.step_name == "slack_notification")
        assert slack_step.status == StepStatus.FAILED
        assert run.overall_status == RunStatus.PARTIAL

        retry_step(session, settings, run, "slack_notification", clients)
        assert slack_step.status == StepStatus.SUCCESS
        assert run.overall_status == RunStatus.COMPLETED


# --- Schedule construction ---------------------------------------------------

class TestSchedule:
    def test_three_events_with_probation_offset(self, settings):
        settings.probation_period_days = 90
        employee = Employee(
            name="Alex Example",
            role="Operations Analyst",
            email="alex.example@company-a.example.com",
            start_date=date(2026, 7, 1),
        )
        events = build_onboarding_events(employee, settings)
        assert len(events) == 3
        assert events[0].start.date() == date(2026, 7, 1)
        assert events[1].start.date() == date(2026, 7, 1)
        assert events[2].start.date() == date(2026, 7, 1).replace(month=9, day=29)
        # all events are start < end
        assert all(ev.start < ev.end for ev in events)


def _raise(*args, **kwargs):
    raise RuntimeError("calendar down")


def _raise_pack(employee, settings):
    raise RuntimeError("weasyprint down")
