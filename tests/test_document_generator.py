"""Welcome pack tests: HTML render content + real PDF generation."""

from datetime import date
from pathlib import Path

from onboarding.document_generator import generate_welcome_pack_pdf, render_welcome_pack_html
from onboarding.models import Employee


def _employee() -> Employee:
    emp = Employee(
        name="Alex Example",
        role="Operations Analyst",
        email="alex.example@company-a.example.com",
        manager_name="Morgan Example",
        start_date=date(2026, 7, 1),
    )
    emp.id = 1
    return emp


class TestRenderHtml:
    def test_contains_hire_and_company_details(self, settings):
        html = render_welcome_pack_html(_employee(), settings)
        assert "Alex Example" in html
        assert "Operations Analyst" in html
        assert settings.company_name in html
        assert settings.it_contact in html
        assert "Morgan Example" in html

    def test_schedule_has_three_sessions(self, settings):
        html = render_welcome_pack_html(_employee(), settings)
        assert "Day 1 induction" in html
        assert "Team intro" in html
        assert "Probation review" in html


class TestGeneratePdf:
    def test_writes_pdf_file(self, settings):
        path = Path(generate_welcome_pack_pdf(_employee(), settings))
        assert path.exists()
        assert path.suffix == ".pdf"
        assert path.read_bytes().startswith(b"%PDF")
