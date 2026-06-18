"""Streamlit tracker for onboarding runs.

Read-only view over the FastAPI service: lists every onboarding run, breaks
each down into its steps with pass/fail indicators, and offers a retry button
per failed step. Trigger a new onboarding from the sidebar.

Run with:  streamlit run tracker/app.py
The API base URL is taken from API_BASE_URL (default http://localhost:8000).
"""

import hmac
import os
from datetime import date

import httpx
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
# Sent to the API when DEMO_MODE=false; ignored (auth is off) in demo mode.
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")
_AUTH_HEADERS = {"X-API-Key": ADMIN_API_KEY} if ADMIN_API_KEY else {}

DEMO_MODE = os.environ.get("DEMO_MODE", "true").strip().lower() not in ("false", "0", "no")
TRACKER_PASSWORD = os.environ.get("TRACKER_PASSWORD", "")


def require_password() -> None:
    """Gate the tracker UI outside demo mode.

    The tracker exposes hire PII and trigger/retry actions, so it must not sit
    open on :8501 in a real deploy. In demo mode it stays open (public demo). In
    production it requires TRACKER_PASSWORD; if that is unset we fail closed
    rather than serve the data unauthenticated.
    """
    if DEMO_MODE:
        return
    if not TRACKER_PASSWORD:
        st.error(
            "Tracker is not configured for production. Set TRACKER_PASSWORD "
            "(and put it behind TLS) before exposing it. Refusing to serve "
            "onboarding data unauthenticated."
        )
        st.stop()
    if st.session_state.get("tracker_authed"):
        return
    st.title("🔒 Onboarding tracker")
    pw = st.text_input("Password", type="password")
    if st.button("Unlock"):
        if hmac.compare_digest(pw, TRACKER_PASSWORD):
            st.session_state["tracker_authed"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    st.stop()

STATUS_BADGE = {
    "COMPLETED": "🟢 COMPLETED",
    "PARTIAL": "🟠 PARTIAL",
    "FAILED": "🔴 FAILED",
    "IN_PROGRESS": "🔵 IN PROGRESS",
    "PENDING": "⚪ PENDING",
}

STEP_ICON = {
    "SUCCESS": "✅",
    "FAILED": "❌",
    "RUNNING": "🔄",
    "PENDING": "⏳",
}

STEP_LABELS = {
    "welcome_email": "Welcome email",
    "calendar_events": "Calendar events",
    "welcome_pack": "Welcome pack PDF",
    "slack_notification": "Slack notification",
}


def api_get(path: str):
    return httpx.get(f"{API_BASE_URL}{path}", headers=_AUTH_HEADERS, timeout=30)


def api_post(path: str, json=None):
    return httpx.post(f"{API_BASE_URL}{path}", json=json, headers=_AUTH_HEADERS, timeout=60)


st.set_page_config(page_title="Trinops Onboarding Tracker", page_icon="🧭", layout="wide")
require_password()
st.title("🧭 Onboarding tracker")
st.caption(f"Connected to {API_BASE_URL}")

# --- Sidebar: trigger a new onboarding ---------------------------------------
with st.sidebar:
    st.header("New hire")
    with st.form("trigger"):
        name = st.text_input("Name", placeholder="Alex Example")
        role = st.text_input("Role", placeholder="Operations Analyst")
        email = st.text_input("Email", placeholder="alex.example@company-a.example.com")
        start_date = st.date_input("Start date", value=date.today())
        slack_handle = st.text_input("Slack handle", placeholder="@alex.example")
        manager_name = st.text_input("Manager", placeholder="Morgan Example")
        submitted = st.form_submit_button("Run onboarding")

    if submitted:
        if not (name and role and email):
            st.error("Name, role and email are required.")
        else:
            resp = api_post(
                "/onboarding/trigger",
                json={
                    "name": name,
                    "role": role,
                    "email": email,
                    "start_date": start_date.isoformat(),
                    "slack_handle": slack_handle or None,
                    "manager_name": manager_name or None,
                },
            )
            if resp.status_code == 201:
                st.success(f"Onboarding triggered for {name}.")
            else:
                st.error(f"Trigger failed ({resp.status_code}): {resp.text}")

    if st.button("Refresh"):
        st.rerun()

# --- Main: list runs ---------------------------------------------------------
try:
    runs_resp = api_get("/onboarding")
except httpx.HTTPError as exc:
    st.error(f"Cannot reach the API at {API_BASE_URL}: {exc}")
    st.stop()

if runs_resp.status_code != 200:
    st.error(f"API returned {runs_resp.status_code}: {runs_resp.text}")
    st.stop()

runs = runs_resp.json()
if not runs:
    st.info("No onboarding runs yet. Trigger one from the sidebar.")
    st.stop()

counts = {"COMPLETED": 0, "PARTIAL": 0, "FAILED": 0}
for r in runs:
    counts[r["overall_status"]] = counts.get(r["overall_status"], 0) + 1
c1, c2, c3 = st.columns(3)
c1.metric("Completed", counts.get("COMPLETED", 0))
c2.metric("Partial", counts.get("PARTIAL", 0))
c3.metric("Failed", counts.get("FAILED", 0))

st.divider()

for run in runs:
    emp = run["employee"]
    badge = STATUS_BADGE.get(run["overall_status"], run["overall_status"])
    title = f"{emp['name']} — {emp['role']}  ·  {badge}"
    with st.expander(title, expanded=run["overall_status"] != "COMPLETED"):
        st.write(
            f"**Start date:** {emp['start_date']}  |  **Email:** {emp['email']}  |  "
            f"**Manager:** {emp.get('manager_name') or '—'}  |  **Run #{run['id']}**"
        )
        for step in run["steps"]:
            icon = STEP_ICON.get(step["status"], "•")
            label = STEP_LABELS.get(step["step_name"], step["step_name"])
            cols = st.columns([4, 2, 2, 2])
            cols[0].markdown(f"{icon} **{label}**")
            cols[1].markdown(f"`{step['status']}`")
            cols[2].markdown(f"attempts: {step['attempts']}")
            if step["status"] == "FAILED":
                if cols[3].button("Retry", key=f"retry-{run['id']}-{step['step_name']}"):
                    rr = api_post(f"/onboarding/{run['id']}/retry/{step['step_name']}")
                    if rr.status_code == 200:
                        st.rerun()
                    else:
                        st.error(f"Retry failed ({rr.status_code}): {rr.text}")
            if step["error_message"]:
                st.caption(f"↳ {step['error_message']}")
            elif step["artifact_path"]:
                st.caption(f"↳ {step['artifact_path']}")
