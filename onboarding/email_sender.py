"""Welcome email rendering: Jinja2 template -> HTML."""

from jinja2 import Environment, FileSystemLoader, select_autoescape

from onboarding.config import Settings
from onboarding.models import Employee

_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html"]),
)


def render_welcome_email(employee: Employee, settings: Settings) -> str:
    template = _env.get_template("welcome_email.html.j2")
    return template.render(
        first_name=employee.first_name,
        full_name=employee.name,
        role=employee.role,
        start_date=employee.start_date.isoformat(),
        manager_name=employee.manager_name or "your manager",
        company_name=settings.company_name,
        company_email=settings.company_email,
        handbook_url=settings.handbook_url,
        it_contact=settings.it_contact,
        people_contact=settings.people_contact,
    )


def welcome_subject(employee: Employee, settings: Settings) -> str:
    return f"Welcome to {settings.company_name}, {employee.first_name}!"
