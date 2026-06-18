"""require_admin: open in demo mode, enforced when a key is configured."""

import pytest
from fastapi import HTTPException

import api.auth as auth
from onboarding.config import Settings


def _use(monkeypatch, **kwargs):
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(_env_file=None, **kwargs))


def test_demo_mode_allows_without_key(monkeypatch):
    _use(monkeypatch, demo_mode=True)
    assert auth.require_admin(x_api_key=None) is None


def test_unconfigured_key_blocks(monkeypatch):
    _use(monkeypatch, demo_mode=False, admin_api_key="")
    with pytest.raises(HTTPException) as exc:
        auth.require_admin(x_api_key="whatever")
    assert exc.value.status_code == 503


def test_missing_header_rejected(monkeypatch):
    _use(monkeypatch, demo_mode=False, admin_api_key="s3cret")
    with pytest.raises(HTTPException) as exc:
        auth.require_admin(x_api_key=None)
    assert exc.value.status_code == 401


def test_wrong_key_rejected(monkeypatch):
    _use(monkeypatch, demo_mode=False, admin_api_key="s3cret")
    with pytest.raises(HTTPException) as exc:
        auth.require_admin(x_api_key="nope")
    assert exc.value.status_code == 401


def test_correct_key_allows(monkeypatch):
    _use(monkeypatch, demo_mode=False, admin_api_key="s3cret")
    assert auth.require_admin(x_api_key="s3cret") is None
