"""Welcome pack PDF: Jinja2 template rendered to PDF by WeasyPrint."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from onboarding.calendar_events import build_onboarding_events
from onboarding.config import Settings
from onboarding.logging_conf import get_logger
from onboarding.models import Employee

logger = get_logger(__name__)

_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html"]),
)


def _schedule_rows(employee: Employee, settings: Settings) -> list[dict[str, str]]:
    rows = []
    for event in build_onboarding_events(employee, settings):
        rows.append(
            {
                "title": event.summary.split(" — ")[0],
                "date": event.start.strftime("%a %d %b %Y"),
                "time": event.start.strftime("%H:%M"),
            }
        )
    return rows


def render_welcome_pack_html(employee: Employee, settings: Settings) -> str:
    template = _env.get_template("welcome_pack.html.j2")
    return template.render(
        full_name=employee.name,
        first_name=employee.first_name,
        role=employee.role,
        start_date=employee.start_date.strftime("%A %d %B %Y"),
        manager_name=employee.manager_name or "your manager",
        company_name=settings.company_name,
        company_address=settings.company_address,
        company_email=settings.company_email,
        handbook_url=settings.handbook_url,
        it_contact=settings.it_contact,
        people_contact=settings.people_contact,
        schedule=_schedule_rows(employee, settings),
    )


def generate_welcome_pack_pdf(employee: Employee, settings: Settings) -> str:
    """Render the welcome pack PDF and return its file path."""
    from weasyprint import HTML  # heavy native deps — imported lazily

    html = render_welcome_pack_html(employee, settings)
    out_dir = Path(settings.pack_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = employee.name.lower().replace(" ", "_")
    path = out_dir / f"welcome_pack_{employee.id}_{safe_name}.pdf"
    HTML(string=html).write_pdf(str(path))
    logger.info("generated welcome pack %s for %s", path, employee.name)
    return str(path)
