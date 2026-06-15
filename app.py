from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from core.auth import DEFAULT_TEMP_PASSWORD, authenticate_user, bootstrap_missing_passwords, set_user_password
from core.db import get_conn, init_db, fetchall, fetchone, execute, now_iso, get_setting, set_setting
from core.payroll_engine import compute_payroll, save_payroll_draft, update_payroll_status, compute_13th_month_basis, save_13th_month_run
from core.pdf_utils import generate_payslip_pdf, generate_13th_month_pdf
from core.import_export import create_required_template_xlsx, import_template_xlsx, import_legacy_payroll_zip, export_full_database_snapshot_xlsx
from core.reviews import build_annual_review_auto_summary
from core.quality import build_payroll_preflight_checks, summarize_checks
from core.drawer import create_drawer_cash_advance_movement, create_missing_cash_advance_drawer_movements
from core.integration_accounting import (
    enqueue_payroll_run, enqueue_13th_month, enqueue_cash_advance_release,
    enqueue_cash_advance_repayment, enqueue_employee_sync, export_outbox_zip, mark_outbox_status,
    post_ready_outbox_to_accounting, post_ready_outbox_to_operations
)
from core.integration_operations import (
    enqueue_operations_snapshot, enqueue_payroll_ready_for_operations,
    enqueue_employee_status_for_operations
)

st.set_page_config(page_title="Hidden Oasis Staff & Payroll", layout="wide", page_icon="🕒")

CSS = """
<style>
.block-container { padding-top: 1.2rem; padding-bottom: 3rem; }

[data-testid="stSidebar"] {
    background: #11151b !important;
}

[data-testid="stSidebar"],
[data-testid="stSidebar"] * {
    color: #f7f7f5 !important;
}

[data-testid="stSidebar"] button {
    background: #2b2d38 !important;
    color: #ffffff !important;
    border: 1px solid #444756 !important;
}

.metric-card { border: 1px solid #e8e4dc; border-radius: 18px; padding: 18px; background: #fffdf8; }
.small-note { color: #666; font-size: 0.9rem; }
.status-pill { border-radius: 999px; padding: 4px 10px; background: #f2efe9; display: inline-block; }
.login-view [data-testid="stSidebar"] { display: none; }
.login-card {
    max-width: 420px;
    margin: 8vh auto 0 auto;
    border: 1px solid #e1e6df;
    border-radius: 22px;
    padding: 30px;
    background: rgba(255,255,255,.92);
    box-shadow: 0 24px 70px rgba(26,38,30,.09);
}
.login-mark {
    width: 48px;
    height: 48px;
    display: grid;
    place-items: center;
    border-radius: 15px;
    background: #5f6f52;
    color: #24262f;
    font-weight: 720;
    letter-spacing: .03em;
    margin-bottom: 18px;
}
.login-title {
    font-size: 2.1rem;
    font-weight: 720;
    line-height: 1;
    letter-spacing: -0.04em;
    margin-bottom: 1.1rem;
}
.login-credit {
    color: #7b8179;
    font-size: 0.8rem;
    margin-top: 1rem;
}

.login-title,
.login-subtitle {
    color: #24262f !important;
    text-shadow: none !important;
}

.login-hero,
.login-card,
.auth-hero {
    color: #24262f !important;
}


/* Login contrast repair */
.login-card {
    background: #f7f7f2 !important;
    color: #24262f !important;
}

.login-title {
    color: #24262f !important;
    text-shadow: none !important;
}

.login-mark {
    color: #ffffff !important;
}

/* Keep the actual login form visually attached to the hero card */
.login-view [data-testid="stForm"] {
    max-width: 420px !important;
    margin: 0 auto !important;
    border: 1px solid #343944 !important;
    border-top: 0 !important;
    border-radius: 0 0 18px 18px !important;
    padding: 22px 30px 28px 30px !important;
    background: #10151c !important;
}

.login-view [data-testid="stForm"] label,
.login-view [data-testid="stForm"] p,
.login-view [data-testid="stForm"] span {
    color: #f7f7f5 !important;
}


/* Login container repair only */
.login-card {
    max-width: 420px !important;
    margin: 8vh auto 0 auto !important;
    border: 1px solid #e1e6df !important;
    border-bottom: 0 !important;
    border-radius: 22px 22px 0 0 !important;
    padding: 30px 30px 24px 30px !important;
    background: rgba(255,255,255,.92) !important;
    color: #24262f !important;
    box-shadow: 0 24px 70px rgba(26,38,30,.09) !important;
}

.login-title {
    color: #24262f !important;
    text-shadow: none !important;
}

.login-mark {
    color: #ffffff !important;
}

.login-view [data-testid="stForm"] {
    max-width: 420px !important;
    margin: 0 auto !important;
    border: 1px solid #e1e6df !important;
    border-top: 0 !important;
    border-radius: 0 0 22px 22px !important;
    padding: 24px 30px 30px 30px !important;
    background: rgba(255,255,255,.92) !important;
    box-shadow: 0 24px 70px rgba(26,38,30,.09) !important;
}

.login-view [data-testid="stForm"] label,
.login-view [data-testid="stForm"] p,
.login-view [data-testid="stForm"] span {
    color: #24262f !important;
}

.login-view [data-testid="stForm"] input,
.login-view [data-testid="stForm"] div[data-baseweb="select"] > div {
    background: #f3f2ef !important;
    color: #24262f !important;
}


/* Accounting-style Staff login */
.login-view .block-container {
    max-width: 760px !important;
    padding-top: 7vh !important;
}

.login-card {
    max-width: 560px !important;
    margin: 0 auto !important;
    border: 1px solid #dfe6dc !important;
    border-bottom: 0 !important;
    border-radius: 26px 26px 0 0 !important;
    padding: 48px 46px 10px 46px !important;
    background: #ffffff !important;
    color: #111111 !important;
    box-shadow: 0 28px 90px rgba(35, 45, 35, .10) !important;
}

.login-mark {
    width: 64px !important;
    height: 64px !important;
    border-radius: 18px !important;
    background: #197044 !important;
    color: #ffffff !important;
    display: grid !important;
    place-items: center !important;
    font-size: 1.35rem !important;
    font-weight: 900 !important;
    letter-spacing: .04em !important;
    margin-bottom: 32px !important;
}

.login-title {
    color: #111111 !important;
    font-size: 3.1rem !important;
    font-weight: 900 !important;
    line-height: .98 !important;
    letter-spacing: -0.055em !important;
    margin: 0 0 22px 0 !important;
    text-shadow: none !important;
}

.login-view [data-testid="stForm"] {
    max-width: 560px !important;
    margin: 0 auto !important;
    border: 1px solid #dfe6dc !important;
    border-top: 0 !important;
    border-radius: 0 0 26px 26px !important;
    padding: 0 46px 46px 46px !important;
    background: #ffffff !important;
    color: #111111 !important;
    box-shadow: 0 28px 90px rgba(35, 45, 35, .10) !important;
}

.login-view [data-testid="stForm"] label,
.login-view [data-testid="stForm"] p,
.login-view [data-testid="stForm"] span {
    color: #525850 !important;
    font-weight: 800 !important;
    font-size: 1rem !important;
}

.login-view [data-testid="stForm"] input,
.login-view [data-baseweb="select"] > div {
    height: 54px !important;
    border-radius: 16px !important;
    background: #ffffff !important;
    color: #111111 !important;
    border-color: #d8ddd5 !important;
}

.login-view [data-testid="stFormSubmitButton"] button {
    width: 100% !important;
    height: 64px !important;
    border-radius: 16px !important;
    background: #111111 !important;
    color: #ffffff !important;
    font-size: 1.15rem !important;
    font-weight: 800 !important;
    border: none !important;
    margin-top: 12px !important;
}

.login-view [data-testid="stFormSubmitButton"] button:hover {
    background: #1e1e1e !important;
    color: #ffffff !important;
}

.login-credit {
    color: #7b8179 !important;
    font-size: 1rem !important;
    margin-top: 26px !important;
}


/* Single-card login fix: Streamlit form is the real card */
.login-view .block-container {
    max-width: 620px !important;
    padding-top: 6vh !important;
}

.login-card {
    max-width: 560px !important;
    margin: 0 auto -1px auto !important;
    border: 1px solid #dfe6dc !important;
    border-bottom: 0 !important;
    border-radius: 26px 26px 0 0 !important;
    padding: 46px 46px 8px 46px !important;
    background: #ffffff !important;
    color: #111111 !important;
    box-shadow: 0 28px 90px rgba(35, 45, 35, .10) !important;
}

.login-mark {
    width: 64px !important;
    height: 64px !important;
    border-radius: 18px !important;
    background: #197044 !important;
    color: #ffffff !important;
    display: grid !important;
    place-items: center !important;
    font-size: 1.35rem !important;
    font-weight: 900 !important;
    letter-spacing: .04em !important;
    margin-bottom: 30px !important;
}

.login-title {
    color: #111111 !important;
    font-size: 3rem !important;
    font-weight: 900 !important;
    line-height: .98 !important;
    letter-spacing: -0.055em !important;
    margin: 0 !important;
    text-shadow: none !important;
}

.login-view [data-testid="stForm"] {
    max-width: 560px !important;
    margin: 0 auto !important;
    border: 1px solid #dfe6dc !important;
    border-top: 0 !important;
    border-radius: 0 0 26px 26px !important;
    padding: 22px 46px 46px 46px !important;
    background: #ffffff !important;
    box-shadow: 0 28px 90px rgba(35, 45, 35, .10) !important;
}

.login-view [data-testid="stForm"] label,
.login-view [data-testid="stForm"] p,
.login-view [data-testid="stForm"] span {
    color: #525850 !important;
    font-weight: 800 !important;
}

.login-view [data-baseweb="select"] > div,
.login-view input {
    min-height: 56px !important;
    border-radius: 16px !important;
    background: #ffffff !important;
    color: #111111 !important;
    border-color: #d8ddd5 !important;
}

.login-view [data-testid="stFormSubmitButton"] button {
    width: 100% !important;
    height: 64px !important;
    border-radius: 16px !important;
    background: #111111 !important;
    color: #ffffff !important;
    font-size: 1.15rem !important;
    font-weight: 800 !important;
    border: none !important;
    margin-top: 12px !important;
}

.login-view [data-testid="stFormSubmitButton"] button:hover {
    background: #1e1e1e !important;
    color: #ffffff !important;
}

.login-credit {
    max-width: 560px !important;
    margin: 18px auto 0 auto !important;
    color: #7b8179 !important;
    font-size: 1rem !important;
}


/* Accounting-proportion Staff login correction */
.login-view .block-container {
    max-width: 560px !important;
    padding-top: 8vh !important;
}

.login-view [data-testid="stForm"] {
    max-width: 520px !important;
    margin: 0 auto !important;
    background: #ffffff !important;
    border: 1px solid #e6e7e4 !important;
    border-radius: 14px !important;
    padding: 34px !important;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.045) !important;
    color: #111110 !important;
}

.login-mark {
    width: 48px !important;
    height: 48px !important;
    border-radius: 15px !important;
    background: #1f6a47 !important;
    color: #ffffff !important;
    font-size: 1rem !important;
    font-weight: 800 !important;
    margin-bottom: 28px !important;
}

.login-title {
    color: #111110 !important;
    font-size: 2.1rem !important;
    font-weight: 720 !important;
    letter-spacing: -0.04em !important;
    line-height: 1 !important;
    margin-bottom: 1.1rem !important;
}

.login-view [data-testid="stForm"] label,
.login-view [data-testid="stForm"] p,
.login-view [data-testid="stForm"] span {
    color: #565b55 !important;
    font-size: 12px !important;
    font-weight: 530 !important;
}

.login-view input,
.login-view [data-baseweb="select"] > div {
    min-height: 42px !important;
    border-radius: 9px !important;
    padding: 9px 11px !important;
    background: #ffffff !important;
    color: #111110 !important;
    border: 1px solid #d7dad4 !important;
    font-weight: 430 !important;
}

.login-view [data-testid="stFormSubmitButton"] button {
    width: auto !important;
    min-height: 42px !important;
    height: 42px !important;
    border-radius: 9px !important;
    padding: 9px 18px !important;
    background: #111111 !important;
    color: #ffffff !important;
    border: 1px solid #111111 !important;
    font-weight: 540 !important;
    font-size: 1rem !important;
}

.login-credit {
    color: #6f736d !important;
    font-size: 0.95rem !important;
    margin-top: 18px !important;
}


/* TRUE Accounting login match */
.login-view .block-container {
    max-width: 520px !important;
    padding-top: 8vh !important;
}

.login-view [data-testid="stForm"] {
    max-width: 520px !important;
    margin: 0 auto 14px auto !important;
    background: #ffffff !important;
    border: 1px solid #e6e7e4 !important;
    border-radius: 14px !important;
    padding: 17px !important;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.045) !important;
    color: #111110 !important;
}

.login-mark {
    width: 48px !important;
    height: 48px !important;
    border-radius: 15px !important;
    background: #1f6a47 !important;
    color: #ffffff !important;
    display: grid !important;
    place-items: center !important;
    font-size: 1rem !important;
    font-weight: 720 !important;
    letter-spacing: .03em !important;
    margin: 0 0 18px 0 !important;
}

.login-title {
    color: #111110 !important;
    font-size: 2.1rem !important;
    font-weight: 720 !important;
    line-height: 1 !important;
    letter-spacing: -0.04em !important;
    margin: 0 0 1.1rem 0 !important;
    text-shadow: none !important;
}

.login-view [data-testid="stForm"] label,
.login-view [data-testid="stForm"] p,
.login-view [data-testid="stForm"] span {
    color: #565b55 !important;
    font-size: 12px !important;
    font-weight: 530 !important;
}

.login-view [data-baseweb="select"] > div,
.login-view input {
    padding: 9px 11px !important;
    border-radius: 9px !important;
    border: 1px solid #d7dad4 !important;
    background: #ffffff !important;
    color: #111110 !important;
    font-weight: 430 !important;
    min-height: 42px !important;
    box-shadow: none !important;
}

.login-view [data-testid="stFormSubmitButton"] button {
    padding: 9px 11px !important;
    border-radius: 9px !important;
    border: 1px solid #111111 !important;
    background: #111111 !important;
    color: #ffffff !important;
    font-weight: 540 !important;
    width: 100% !important;
    min-height: 44px !important;
    margin-top: 8px !important;
}

.login-credit {
    color: #6f736d !important;
    font-size: 0.95rem !important;
    margin-top: 14px !important;
}

</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

conn = get_conn()
init_db(conn)
bootstrapped_passwords = bootstrap_missing_passwords(conn)


def money(v: float | int | None) -> str:
    return f"₱{float(v or 0):,.2f}"


def iso(d: date | str | None) -> str:
    if d is None:
        return ""
    return d.isoformat() if isinstance(d, date) else str(d)


def df_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    rows = fetchall(conn, sql, params)
    return pd.DataFrame(rows)


def employees(active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM employees"
    if active_only:
        sql += " WHERE status NOT IN ('Inactive','Terminated')"
    sql += " ORDER BY full_name"
    return fetchall(conn, sql)


def emp_options(active_only: bool = True) -> dict[str, int]:
    emps = employees(active_only)
    return {f"{e['full_name']} ({e['employee_code']})": e["id"] for e in emps}


def show_table(title: str, sql: str, params: tuple = (), use_container_width: bool = True):
    st.subheader(title)
    df = df_query(sql, params)
    if df.empty:
        st.info("No records yet.")
    else:
        st.dataframe(df, use_container_width=use_container_width, hide_index=True)


def audit(actor: str, action: str, table: str, record_id: int | None, details: str = ""):
    execute(
        conn,
        "INSERT INTO audit_logs(actor, action, table_name, record_id, details, created_at) VALUES(?,?,?,?,?,?)",
        (actor, action, table, record_id, details, now_iso()),
    )


if "auth_user" not in st.session_state:
    st.session_state["auth_user"] = None

if st.session_state["auth_user"] is None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none; }

        .stApp {
            background:
                radial-gradient(circle at 0 0, #f8fbf9 0, transparent 30%),
                radial-gradient(circle at 100% 100%, #edf5f0 0, transparent 26%),
                #f6f6f4 !important;
            color: #111110 !important;
        }

        .block-container {
            max-width: 560px !important;
            padding-top: 8vh !important;
        }

        .login-view [data-testid="stForm"] {
            background: #ffffff !important;
            border: 1px solid #e6e7e4 !important;
            border-radius: 14px !important;
            padding: 34px !important;
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.045) !important;
            color: #111110 !important;
        }

        .login-mark {
            width: 64px;
            height: 64px;
            border-radius: 18px;
            background: #1f6a47;
            color: #ffffff;
            display: grid;
            place-items: center;
            font-size: 1.35rem;
            font-weight: 800;
            letter-spacing: .04em;
            margin-bottom: 28px;
        }

        .login-title {
            color: #111110 !important;
            font-size: 3rem !important;
            font-weight: 700 !important;
            letter-spacing: -0.05em !important;
            line-height: 1 !important;
            margin: 0 0 30px 0 !important;
        }

        .login-view label,
        .login-view [data-testid="stMarkdownContainer"] p,
        .login-view span {
            color: #565b55 !important;
            font-weight: 650 !important;
        }

        .login-view input,
        .login-view [data-baseweb="select"] > div {
            background: #ffffff !important;
            color: #111110 !important;
            border: 1px solid #d7dad4 !important;
            border-radius: 9px !important;
            min-height: 46px !important;
        }

        .login-view [data-testid="stFormSubmitButton"] button {
            background: #111111 !important;
            color: #ffffff !important;
            border: 1px solid #111111 !important;
            border-radius: 9px !important;
            min-height: 46px !important;
            width: 100% !important;
            font-weight: 650 !important;
            margin-top: 10px !important;
        }

        .login-credit {
            color: #6f736d !important;
            font-size: 0.95rem !important;
            margin-top: 22px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div class='login-view'>", unsafe_allow_html=True)

    if bootstrapped_passwords:
        st.warning(f"Temporary passwords were created for {bootstrapped_passwords} existing user(s). Use `{DEFAULT_TEMP_PASSWORD}` once, then change the password immediately.")

    active_users = fetchall(conn, "SELECT display_name FROM app_users WHERE active=1 ORDER BY display_name")
    user_names = [u["display_name"] for u in active_users]

    if not user_names:
        st.error("No active app users exist. Add an Owner user directly in the database or reinitialize the local prototype database.")
        st.stop()

    with st.form("login_form"):
        st.markdown(
            """
            <div class="login-mark">HO</div>
            <div class="login-title">Staff & Payroll</div>
            """,
            unsafe_allow_html=True,
        )

        login_name = st.selectbox("User", user_names)
        login_password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")

        st.markdown("<div class='login-credit'>by C.M.</div>", unsafe_allow_html=True)

        if submitted:
            user = authenticate_user(conn, login_name, login_password)
            if not user:
                st.error("Invalid user or password.")
            else:
                st.session_state["auth_user"] = {
                    "id": user["id"],
                    "display_name": user["display_name"],
                    "role": user["role"],
                    "must_change_password": int(user.get("must_change_password") or 0),
                }
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

st.sidebar.title("Hidden Oasis")
st.sidebar.caption("Staff • Attendance • Payroll • Integrations")

current_user = st.session_state["auth_user"]["display_name"]
current_role = st.session_state["auth_user"]["role"]
set_setting(conn, "current_user", current_user)
set_setting(conn, "current_role", current_role)
st.sidebar.caption(f"Signed in: {current_user}")
st.sidebar.caption(f"Role: {current_role}")

if st.sidebar.button("Sign out"):
    st.session_state["auth_user"] = None
    st.rerun()

if st.session_state["auth_user"].get("must_change_password"):
    st.title("Change Temporary Password")
    st.warning("This account is using a temporary password. Set a new password before continuing.")
    with st.form("force_password_change"):
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        submitted = st.form_submit_button("Update Password", type="primary")
        if submitted:
            if len(new_password) < 8:
                st.error("Use at least 8 characters.")
            elif new_password != confirm_password:
                st.error("Passwords do not match.")
            else:
                set_user_password(conn, int(st.session_state["auth_user"]["id"]), new_password, must_change=False)
                st.session_state["auth_user"]["must_change_password"] = 0
                audit(current_user, "Changed temporary password", "app_users", int(st.session_state["auth_user"]["id"]))
                st.success("Password updated.")
                st.rerun()
    st.stop()

def can_review_payroll() -> bool:
    return current_role in ("Owner", "Manager")

def can_supervise() -> bool:
    return current_role in ("Owner", "Manager", "Supervisor", "Reception")

def has_role(*roles: str) -> bool:
    return current_role in roles

def require_roles(*roles: str) -> bool:
    if has_role(*roles):
        return True
    st.error("You do not have permission for this action.")
    audit(current_user, "Denied permission", "app_users", int(st.session_state["auth_user"]["id"]), f"required={roles}; role={current_role}")
    return False

page = st.sidebar.radio(
    "Go to",
    [
        "Home",
        "Staff",
        "Schedules & Logs",
        "Attendance Review",
        "Leaves",
        "Cash Advances",
        "Freelance Outputs",
        "Data Import / Templates",
        "Payroll",
        "Payroll QA",
        "Accounting Sync",
        "Operations Sync",
        "Payslips",
        "13th Month Pay",
        "Infractions & Memos",
        "Annual Reviews",
        "Reports",
        "Access Control",
        "Settings",
    ],
)

PAGE_ROLES = {
    "Home": ("Owner", "Manager", "Supervisor", "Reception", "Payroll Clerk", "Viewer"),
    "Staff": ("Owner", "Manager", "Payroll Clerk"),
    "Schedules & Logs": ("Owner", "Manager", "Supervisor", "Reception", "Payroll Clerk"),
    "Attendance Review": ("Owner", "Manager", "Supervisor", "Reception"),
    "Leaves": ("Owner", "Manager", "Supervisor", "Payroll Clerk"),
    "Cash Advances": ("Owner", "Manager", "Payroll Clerk"),
    "Freelance Outputs": ("Owner", "Manager", "Payroll Clerk"),
    "Data Import / Templates": ("Owner", "Manager"),
    "Payroll": ("Owner", "Manager", "Payroll Clerk"),
    "Payroll QA": ("Owner", "Manager", "Payroll Clerk"),
    "Accounting Sync": ("Owner", "Manager", "Payroll Clerk"),
    "Operations Sync": ("Owner", "Manager", "Supervisor"),
    "Payslips": ("Owner", "Manager", "Payroll Clerk"),
    "13th Month Pay": ("Owner", "Manager", "Payroll Clerk"),
    "Infractions & Memos": ("Owner", "Manager", "Supervisor"),
    "Annual Reviews": ("Owner", "Manager", "Supervisor"),
    "Reports": ("Owner", "Manager", "Payroll Clerk", "Viewer"),
    "Access Control": ("Owner",),
    "Settings": ("Owner",),
}
if page in PAGE_ROLES and not has_role(*PAGE_ROLES[page]):
    st.title(page)
    st.error("You do not have permission to view this page.")
    audit(current_user, "Denied page access", "app_users", int(st.session_state["auth_user"]["id"]), f"page={page}; role={current_role}")
    st.stop()

if page == "Home":
    st.title("Staff & Payroll Command Center")
    st.caption("V6 prototype preserving the uploaded payroll logic direction: actual-hours base, semi-monthly payroll, SSS MTD catch-up, declared PhilHealth/Pag-IBIG, supervisor-approved OT, leaves, cash advances, and freelancer outputs.")

    c1, c2, c3, c4 = st.columns(4)
    staff_count = fetchone(conn, "SELECT COUNT(*) AS c FROM employees WHERE status='Active'")["c"]
    pending_logs = fetchone(conn, "SELECT COUNT(*) AS c FROM time_logs WHERE attendance_status='Pending'")["c"]
    pending_leaves = fetchone(conn, "SELECT COUNT(*) AS c FROM leave_requests WHERE status='Pending'")["c"]
    open_ca = fetchone(conn, "SELECT COALESCE(SUM(outstanding_balance),0) AS c FROM cash_advances WHERE outstanding_balance > 0")["c"]
    c1.metric("Active Staff", staff_count)
    c2.metric("Pending Attendance", pending_logs)
    c3.metric("Pending Leaves", pending_leaves)
    c4.metric("Cash Advance Balance", money(open_ca))

    st.markdown("### Intended flow")
    st.code(
        """Biometric logs / manual logs
→ Supervisor attendance review
→ Approved OT / leaves / corrections
→ Payroll draft
→ Owner review
→ Approved / Paid / Locked payroll
→ Accounting export queue"""
    )

    st.markdown("### What is included in this first zip")
    st.write(
        "Employee setup, benefits toggles, schedules, time logs, basic biometric CSV/Excel import, attendance review, configurable leaves, cash advances, freelancer/output pay, payroll computation, payroll status locking, payslip PDFs, 13th month pay, infractions, memos, annual reviews, reports, and settings."
    )

elif page == "Staff":
    st.title("Staff Master File")
    tabs = st.tabs(["Employees", "Add Employee", "Edit Employee", "Status History"])

    with tabs[0]:
        show_table(
            "Current Employees",
            """
            SELECT employee_code, full_name, department, position, employment_type, status,
                   hourly_rate, daily_rate, declared_monthly_base,
                   benefits_sss, benefits_philhealth, benefits_pagibig, benefits_tax,
                   standard_shift_hours, unpaid_break_minutes, security_no_break
            FROM employees ORDER BY full_name
            """,
        )

    with tabs[1]:
        st.subheader("Add Employee")
        with st.form("add_employee"):
            col1, col2, col3 = st.columns(3)
            code = col1.text_input("Employee Code", placeholder="EMP-004")
            name = col2.text_input("Full Name")
            dept = col3.selectbox("Department", [d["name"] for d in fetchall(conn, "SELECT name FROM departments WHERE active=1 ORDER BY name")])
            col4, col5, col6 = st.columns(3)
            position = col4.text_input("Position")
            emp_type = col5.selectbox("Employment Type", ["Hourly", "Daily", "Monthly but Actual Hours", "Freelance", "On-call"])
            status = col6.selectbox("Status", ["Active", "Probationary", "Regular", "Part-time", "On-call", "Suspended", "Resigned", "Terminated", "Inactive"])
            col7, col8, col9 = st.columns(3)
            hourly = col7.number_input("Hourly Rate", min_value=0.0, step=5.0)
            daily = col8.number_input("Daily Rate", min_value=0.0, step=50.0)
            declared = col9.number_input("Declared Monthly Base for Benefits", min_value=0.0, step=500.0)
            col10, col11, col12 = st.columns(3)
            shift_hours = col10.number_input("Standard Shift Hours", min_value=0.0, value=9.0, step=0.5)
            break_mins = col11.number_input("Unpaid Break Minutes", min_value=0, value=60, step=15)
            no_break = col12.checkbox("Security/No Break Deduction")
            st.markdown("Benefit toggles")
            b1, b2, b3, b4 = st.columns(4)
            sss = b1.checkbox("SSS", value=True)
            ph = b2.checkbox("PhilHealth", value=True)
            pi = b3.checkbox("Pag-IBIG", value=True)
            tax = b4.checkbox("Withholding Tax", value=False)
            cdate, rdate = st.columns(2)
            start_date = cdate.date_input("Start Date", value=date.today())
            reg_date = rdate.date_input("Regularization Date", value=date.today() + timedelta(days=180))
            supervisor = st.text_input("Supervisor")
            emergency = st.text_input("Emergency Contact")
            notes = st.text_area("Notes")
            submitted = st.form_submit_button("Save Employee")
            if submitted:
                if not code or not name:
                    st.error("Employee code and full name are required.")
                else:
                    try:
                        execute(
                            conn,
                            """
                            INSERT INTO employees(employee_code, full_name, department, position, employment_type, status,
                            hourly_rate, daily_rate, declared_monthly_base, standard_shift_hours, unpaid_break_minutes,
                            security_no_break, benefits_sss, benefits_philhealth, benefits_pagibig, benefits_tax,
                            start_date, regularization_date, supervisor, emergency_contact, notes, created_at, updated_at)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (code, name, dept, position, emp_type, status, hourly, daily, declared, shift_hours, int(break_mins), int(no_break),
                             int(sss), int(ph), int(pi), int(tax), iso(start_date), iso(reg_date), supervisor, emergency, notes, now_iso(), now_iso()),
                        )
                        st.success("Employee saved.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not save employee: {e}")

    with tabs[2]:
        opts = emp_options(False)
        if not opts:
            st.info("No employees yet.")
        else:
            selected = st.selectbox("Select employee", list(opts.keys()))
            emp_id = opts[selected]
            emp = fetchone(conn, "SELECT * FROM employees WHERE id=?", (emp_id,))
            with st.form("edit_employee"):
                c1, c2, c3 = st.columns(3)
                name = c1.text_input("Full Name", emp["full_name"])
                dept = c2.text_input("Department", emp["department"])
                position = c3.text_input("Position", emp["position"])
                c4, c5, c6 = st.columns(3)
                emp_type = c4.selectbox("Employment Type", ["Hourly", "Daily", "Monthly but Actual Hours", "Freelance", "On-call"], index=["Hourly", "Daily", "Monthly but Actual Hours", "Freelance", "On-call"].index(emp["employment_type"]) if emp["employment_type"] in ["Hourly", "Daily", "Monthly but Actual Hours", "Freelance", "On-call"] else 0)
                status = c5.selectbox("Status", ["Active", "Probationary", "Regular", "Part-time", "On-call", "Suspended", "Resigned", "Terminated", "Inactive"], index=["Active", "Probationary", "Regular", "Part-time", "On-call", "Suspended", "Resigned", "Terminated", "Inactive"].index(emp["status"]) if emp["status"] in ["Active", "Probationary", "Regular", "Part-time", "On-call", "Suspended", "Resigned", "Terminated", "Inactive"] else 0)
                declared = c6.number_input("Declared Monthly Base", min_value=0.0, value=float(emp["declared_monthly_base"] or 0), step=500.0)
                c7, c8, c9 = st.columns(3)
                hourly = c7.number_input("Hourly Rate", min_value=0.0, value=float(emp["hourly_rate"] or 0), step=5.0)
                daily = c8.number_input("Daily Rate", min_value=0.0, value=float(emp["daily_rate"] or 0), step=50.0)
                break_mins = c9.number_input("Unpaid Break Minutes", min_value=0, value=int(emp["unpaid_break_minutes"] or 0), step=15)
                b1, b2, b3, b4, b5 = st.columns(5)
                sss = b1.checkbox("SSS", value=bool(emp["benefits_sss"]))
                ph = b2.checkbox("PhilHealth", value=bool(emp["benefits_philhealth"]))
                pi = b3.checkbox("Pag-IBIG", value=bool(emp["benefits_pagibig"]))
                tax = b4.checkbox("Tax", value=bool(emp["benefits_tax"]))
                no_break = b5.checkbox("No Break", value=bool(emp["security_no_break"]))
                reason = st.text_input("Status change reason / edit note")
                submitted = st.form_submit_button("Update Employee")
                if submitted:
                    old_status = emp["status"]
                    execute(
                        conn,
                        """
                        UPDATE employees SET full_name=?, department=?, position=?, employment_type=?, status=?,
                        hourly_rate=?, daily_rate=?, declared_monthly_base=?, unpaid_break_minutes=?, security_no_break=?,
                        benefits_sss=?, benefits_philhealth=?, benefits_pagibig=?, benefits_tax=?, updated_at=? WHERE id=?
                        """,
                        (name, dept, position, emp_type, status, hourly, daily, declared, int(break_mins), int(no_break),
                         int(sss), int(ph), int(pi), int(tax), now_iso(), emp_id),
                    )
                    if old_status != status:
                        execute(conn, "INSERT INTO employee_status_history(employee_id, old_status, new_status, reason, effective_date, changed_by, created_at) VALUES(?,?,?,?,?,?,?)", (emp_id, old_status, status, reason, iso(date.today()), "Admin", now_iso()))
                    st.success("Employee updated.")
                    st.rerun()

    with tabs[3]:
        show_table("Status History", "SELECT e.full_name, h.old_status, h.new_status, h.reason, h.effective_date, h.changed_by, h.created_at FROM employee_status_history h JOIN employees e ON e.id=h.employee_id ORDER BY h.created_at DESC")

elif page == "Schedules & Logs":
    st.title("Schedules & Time Logs")
    tabs = st.tabs(["Schedules", "Manual Time Log", "Biometric CSV Import", "All Logs"])
    opts = emp_options(True)

    with tabs[0]:
        st.subheader("Add Schedule")
        if opts:
            with st.form("add_schedule"):
                emp_label = st.selectbox("Employee", list(opts.keys()))
                work_date = st.date_input("Work Date", value=date.today())
                c1, c2, c3 = st.columns(3)
                shift_start = c1.time_input("Shift Start", value=datetime.strptime("08:00", "%H:%M").time())
                shift_end = c2.time_input("Shift End", value=datetime.strptime("17:00", "%H:%M").time())
                break_mins = c3.number_input("Break Minutes", min_value=0, value=60, step=15)
                department = st.text_input("Department / Area", value="")
                rest = st.checkbox("Rest Day")
                notes = st.text_area("Notes")
                submitted = st.form_submit_button("Save Schedule")
                if submitted:
                    try:
                        execute(conn, "INSERT INTO schedules(employee_id, work_date, shift_start, shift_end, break_minutes, department, is_rest_day, notes) VALUES(?,?,?,?,?,?,?,?)", (opts[emp_label], iso(work_date), shift_start.strftime("%H:%M"), shift_end.strftime("%H:%M"), int(break_mins), department, int(rest), notes))
                        st.success("Schedule saved.")
                    except Exception as e:
                        st.error(f"Schedule not saved: {e}")
        show_table("Schedules", "SELECT s.work_date, e.full_name, s.shift_start, s.shift_end, s.break_minutes, s.department, s.is_rest_day, s.notes FROM schedules s JOIN employees e ON e.id=s.employee_id ORDER BY s.work_date DESC, e.full_name LIMIT 200")

    with tabs[1]:
        st.subheader("Manual Time Log")
        if opts:
            with st.form("manual_log"):
                emp_label = st.selectbox("Employee", list(opts.keys()), key="tl_emp")
                work_date = st.date_input("Work Date", value=date.today(), key="tl_date")
                c1, c2, c3 = st.columns(3)
                actual_in = c1.time_input("Actual In", value=datetime.strptime("08:00", "%H:%M").time())
                actual_out = c2.time_input("Actual Out", value=datetime.strptime("17:00", "%H:%M").time())
                absent = c3.checkbox("Mark Absent")
                c4, c5, c6 = st.columns(3)
                verification = c4.selectbox("Verification", ["Manual", "Biometric", "Reception Verified", "Manager Approved"])
                ot_status = c5.selectbox("OT Status", ["None", "Pending", "Approved", "Rejected"])
                approved_ot = c6.number_input("Approved OT Hours", min_value=0.0, step=0.25)
                reason_cat = st.selectbox("OT Reason", ["", "High guest volume", "High cafe/customer volume", "Event/function", "Owner request", "Supervisor request", "Guest issue", "Emergency maintenance", "Delayed handover", "Staff shortage", "Closing duties", "Inventory/counting", "Other"])
                notes = st.text_area("Notes / reason")
                submitted = st.form_submit_button("Save Time Log")
                if submitted:
                    execute(
                        conn,
                        """
                        INSERT OR IGNORE INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type, is_absent,
                        approved_ot_hours, ot_status, ot_reason_category, ot_reason_note, attendance_status, notes, created_at, updated_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (opts[emp_label], iso(work_date), actual_in.strftime("%H:%M"), actual_out.strftime("%H:%M"), "manual", verification, int(absent),
                         float(approved_ot), ot_status, reason_cat, notes, "Pending", notes, now_iso(), now_iso()),
                    )
                    st.success("Time log saved for review.")

    with tabs[2]:
        st.subheader("Basic Biometric CSV/Excel Import")
        st.caption("Temporary generic importer until the final facial/fingerprint device export format is known. It supports either one timestamp per punch or one row with Time In/Time Out.")
        file = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx"])
        if file:
            try:
                if file.name.lower().endswith("csv"):
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)
                st.write("Preview")
                st.dataframe(df.head(20), use_container_width=True)
                columns = list(df.columns)
                with st.form("import_bio"):
                    mode = st.radio("Import mode", ["Timestamp rows: one punch per row", "Daily rows: has Time In and Time Out"], horizontal=True)
                    emp_code_col = st.selectbox("Employee ID/Code column", columns)
                    device_col = st.selectbox("Device ID column (optional)", [""] + columns)
                    if mode.startswith("Timestamp"):
                        timestamp_col = st.selectbox("Timestamp column", columns, help="Example: 2026-06-08 08:01")
                        punch_col = st.selectbox("Punch Type column (optional)", [""] + columns, help="If present, values like IN/OUT are kept for future device-specific logic. Basic import still groups earliest as in and latest as out.")
                        date_col = time_in_col = time_out_col = ""
                    else:
                        date_col = st.selectbox("Date column", columns)
                        time_in_col = st.selectbox("Time In column", columns)
                        time_out_col = st.selectbox("Time Out column", [""] + columns)
                        timestamp_col = punch_col = ""
                    imported_by = st.text_input("Imported by", value="Admin")
                    submitted = st.form_submit_button("Import biometric logs")
                    if submitted:
                        profile_note = f"Basic biometric import mode: {mode}"
                        cur = execute(conn, "INSERT INTO biometric_import_batches(file_name, imported_at, imported_by, row_count, notes) VALUES(?,?,?,?,?)", (file.name, now_iso(), imported_by, int(len(df)), profile_note))
                        batch_id = cur.lastrowid
                        imported = 0
                        missing = []
                        grouped = {}
                        if mode.startswith("Timestamp"):
                            for _, row in df.iterrows():
                                code = str(row[emp_code_col]).strip()
                                emp = fetchone(conn, "SELECT id FROM employees WHERE employee_code=?", (code,))
                                if not emp:
                                    missing.append(code)
                                    continue
                                ts = pd.to_datetime(row[timestamp_col], errors="coerce")
                                if pd.isna(ts):
                                    continue
                                key = (emp["id"], ts.date().isoformat(), code, str(row[device_col]).strip() if device_col else "")
                                grouped.setdefault(key, []).append(ts.strftime("%H:%M"))
                            for (employee_id, work_date, code, device_id), times in grouped.items():
                                times_sorted = sorted(set(times))
                                actual_in = times_sorted[0]
                                actual_out = times_sorted[-1] if len(times_sorted) > 1 else None
                                execute(conn, """
                                INSERT OR IGNORE INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type, biometric_batch_id, device_employee_code, device_id, attendance_status, notes, created_at, updated_at)
                                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                                """, (employee_id, work_date, actual_in, actual_out, "biometric", "Face/Fingerprint", batch_id, code, device_id, "Pending", profile_note, now_iso(), now_iso()))
                                imported += 1
                        else:
                            for _, row in df.iterrows():
                                code = str(row[emp_code_col]).strip()
                                emp = fetchone(conn, "SELECT id FROM employees WHERE employee_code=?", (code,))
                                if not emp:
                                    missing.append(code)
                                    continue
                                work_date = pd.to_datetime(row[date_col], errors="coerce")
                                if pd.isna(work_date):
                                    continue
                                def fmt_time(v):
                                    if pd.isna(v) or str(v).strip()=="":
                                        return None
                                    parsed = pd.to_datetime(v, errors="coerce")
                                    if not pd.isna(parsed):
                                        return parsed.strftime("%H:%M")
                                    return str(v).strip()[:5]
                                actual_in = fmt_time(row[time_in_col])
                                actual_out = fmt_time(row[time_out_col]) if time_out_col else None
                                device_id = str(row[device_col]).strip() if device_col else ""
                                execute(conn, """
                                INSERT OR IGNORE INTO time_logs(employee_id, work_date, actual_in, actual_out, source, verification_type, biometric_batch_id, device_employee_code, device_id, attendance_status, notes, created_at, updated_at)
                                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                                """, (emp["id"], work_date.date().isoformat(), actual_in, actual_out, "biometric", "Face/Fingerprint", batch_id, code, device_id, "Pending", profile_note, now_iso(), now_iso()))
                                imported += 1
                        st.success(f"Imported {imported} daily biometric log(s). Missing employee codes: {sorted(set(missing))[:10]}")
                        st.info("Imported logs are Pending by design. Supervisor review still decides OT, missing punches, disputes, and corrections before payroll.")
            except Exception as e:
                st.error(f"Import failed: {e}")

    with tabs[3]:
        show_table("Time Logs", "SELECT tl.work_date, e.full_name, tl.actual_in, tl.actual_out, tl.source, tl.verification_type, tl.attendance_status, tl.ot_status, tl.approved_ot_hours, tl.ot_reason_category, tl.reference_occupancy, tl.reference_guest_count, tl.reference_order_count, tl.reference_sales, tl.reference_event_flag, tl.notes FROM time_logs tl JOIN employees e ON e.id=tl.employee_id ORDER BY tl.work_date DESC, e.full_name LIMIT 300")

elif page == "Attendance Review":
    st.title("Supervisor Attendance Review")
    st.caption("Normal biometric logs may be accepted, but lates, missing outs, OT, absences, and corrections should be reviewed before payroll.")
    df = df_query(
        """
        SELECT tl.id, tl.work_date, e.full_name, e.department, tl.actual_in, tl.actual_out, tl.source,
               tl.verification_type, tl.attendance_status, tl.ot_status, tl.approved_ot_hours, tl.ot_reason_category, tl.reference_occupancy, tl.reference_guest_count, tl.reference_order_count, tl.reference_sales, tl.reference_event_flag, tl.notes
        FROM time_logs tl JOIN employees e ON e.id=tl.employee_id
        WHERE tl.attendance_status IN ('Pending','Needs Manager','Disputed') OR tl.ot_status='Pending'
        ORDER BY tl.work_date DESC, e.full_name
        """
    )
    if df.empty:
        st.success("No pending attendance exceptions.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
        selected_id = st.selectbox("Select log ID to review", df["id"].tolist())
        row = fetchone(conn, "SELECT * FROM time_logs WHERE id=?", (int(selected_id),))
        with st.form("review_log"):
            decision = st.selectbox("Decision", ["Accepted", "Verified", "Needs Manager", "Disputed", "Rejected"])
            ot_status = st.selectbox("OT Status", ["None", "Approved", "Rejected", "Pending"], index=1 if row["ot_status"] == "Approved" else 0)
            approved_ot = st.number_input("Approved OT Hours", min_value=0.0, value=float(row["approved_ot_hours"] or 0), step=0.25)
            reason = st.selectbox("Reason Category", ["", "High guest volume", "High cafe/customer volume", "Event/function", "Owner request", "Supervisor request", "Guest issue", "Emergency maintenance", "Delayed handover", "Staff shortage", "Closing duties", "Inventory/counting", "Other"])
            reviewer = st.text_input("Reviewed by", value=current_user if can_supervise() else "Supervisor")
            st.markdown("Operational reference for OT / exception review")
            rc1, rc2, rc3, rc4, rc5 = st.columns(5)
            occupancy = rc1.number_input("Occupancy / rooms", min_value=0.0, value=float(row.get("reference_occupancy") or 0), step=1.0)
            guests = rc2.number_input("Guest count", min_value=0, value=int(row.get("reference_guest_count") or 0), step=1)
            orders = rc3.number_input("POS orders", min_value=0, value=int(row.get("reference_order_count") or 0), step=1)
            sales = rc4.number_input("Sales reference", min_value=0.0, value=float(row.get("reference_sales") or 0), step=100.0)
            event_flag = rc5.checkbox("Event/function", value=bool(row.get("reference_event_flag") or 0))
            notes = st.text_area("Review notes")
            submitted = st.form_submit_button("Save Review")
            if submitted:
                execute(conn, "UPDATE time_logs SET attendance_status=?, ot_status=?, approved_ot_hours=?, ot_reason_category=?, ot_reason_note=?, reference_occupancy=?, reference_guest_count=?, reference_order_count=?, reference_sales=?, reference_event_flag=?, reviewed_by=?, reviewed_at=?, updated_at=? WHERE id=?", (decision, ot_status, float(approved_ot), reason, notes, float(occupancy), int(guests), int(orders), float(sales), int(event_flag), reviewer, now_iso(), now_iso(), int(selected_id)))
                execute(conn, "INSERT INTO attendance_reviews(time_log_id, reviewer, decision, reason, approved_ot_hours, created_at) VALUES(?,?,?,?,?,?)", (int(selected_id), reviewer, decision, notes, float(approved_ot), now_iso()))
                st.success("Review saved.")
                st.rerun()

elif page == "Leaves":
    st.title("Leaves & Entitlements")
    tabs = st.tabs(["Leave Types", "Employee Entitlements", "Leave Requests", "Balances"])
    with tabs[0]:
        st.subheader("Configurable Leave Types")
        with st.form("leave_type"):
            c1, c2, c3, c4 = st.columns(4)
            name = c1.text_input("Leave Name")
            credits = c2.number_input("Default Credits", min_value=0.0, step=0.5)
            paid = c3.checkbox("Paid", value=True)
            statutory = c4.checkbox("Statutory/Mandated", value=False)
            notes = st.text_area("Notes")
            submitted = st.form_submit_button("Add Leave Type")
            if submitted and name:
                execute(conn, "INSERT OR IGNORE INTO leave_types(name, default_credits, paid, statutory, notes) VALUES(?,?,?,?,?)", (name, float(credits), int(paid), int(statutory), notes))
                st.success("Leave type added.")
        show_table("Leave Types", "SELECT name, default_credits, paid, statutory, requires_approval, annual_reset, active, notes FROM leave_types ORDER BY name")

    with tabs[1]:
        opts = emp_options(True)
        types = fetchall(conn, "SELECT * FROM leave_types WHERE active=1 ORDER BY name")
        if opts and types:
            with st.form("entitlement"):
                emp_label = st.selectbox("Employee", list(opts.keys()))
                lt_label = st.selectbox("Leave Type", [t["name"] for t in types])
                lt = next(t for t in types if t["name"] == lt_label)
                year = st.number_input("Year", value=date.today().year, step=1)
                entitled = st.checkbox("Entitled", value=True)
                credits = st.number_input("Credits", min_value=0.0, value=float(lt["default_credits"] or 0), step=0.5)
                submitted = st.form_submit_button("Save Entitlement")
                if submitted:
                    execute(conn, """
                    INSERT INTO employee_leave_entitlements(employee_id, leave_type_id, year, entitled, credits, used)
                    VALUES(?,?,?,?,?,0)
                    ON CONFLICT(employee_id, leave_type_id, year)
                    DO UPDATE SET entitled=excluded.entitled, credits=excluded.credits
                    """, (opts[emp_label], lt["id"], int(year), int(entitled), float(credits)))
                    st.success("Entitlement saved.")
        show_table("Employee Entitlements", "SELECT e.full_name, lt.name, el.year, el.entitled, el.credits, el.used, (el.credits-el.used) AS remaining FROM employee_leave_entitlements el JOIN employees e ON e.id=el.employee_id JOIN leave_types lt ON lt.id=el.leave_type_id ORDER BY e.full_name, lt.name")

    with tabs[2]:
        opts = emp_options(True)
        types = fetchall(conn, "SELECT * FROM leave_types WHERE active=1 ORDER BY name")
        if opts and types:
            with st.form("leave_request"):
                emp_label = st.selectbox("Employee", list(opts.keys()), key="lr_emp")
                lt_label = st.selectbox("Leave Type", [t["name"] for t in types], key="lr_type")
                start = st.date_input("Start Date", value=date.today())
                end = st.date_input("End Date", value=date.today())
                days = st.number_input("Days", min_value=0.0, value=1.0, step=0.5)
                status = st.selectbox("Status", ["Pending", "Approved", "Rejected", "Cancelled"])
                reason = st.text_area("Reason")
                reviewed_by = st.text_input("Reviewed by")
                submitted = st.form_submit_button("Save Leave Request")
                if submitted:
                    lt = next(t for t in types if t["name"] == lt_label)
                    execute(conn, "INSERT INTO leave_requests(employee_id, leave_type_id, start_date, end_date, days, paid, status, reason, reviewed_by, reviewed_at, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (opts[emp_label], lt["id"], iso(start), iso(end), float(days), int(lt["paid"]), status, reason, reviewed_by, now_iso() if status != "Pending" else None, now_iso()))
                    if status == "Approved":
                        ent = fetchone(conn, "SELECT * FROM employee_leave_entitlements WHERE employee_id=? AND leave_type_id=? AND year=?", (opts[emp_label], lt["id"], start.year))
                        if ent:
                            execute(conn, "UPDATE employee_leave_entitlements SET used=used+? WHERE id=?", (float(days), ent["id"]))
                    st.success("Leave request saved.")
        show_table("Leave Requests", "SELECT lr.id, e.full_name, lt.name AS leave_type, lr.start_date, lr.end_date, lr.days, lr.paid, lr.status, lr.reason, lr.reviewed_by FROM leave_requests lr JOIN employees e ON e.id=lr.employee_id JOIN leave_types lt ON lt.id=lr.leave_type_id ORDER BY lr.start_date DESC")

    with tabs[3]:
        show_table("Leave Balances", "SELECT e.full_name, lt.name AS leave_type, el.year, el.entitled, el.credits, el.used, (el.credits-el.used) AS remaining FROM employee_leave_entitlements el JOIN employees e ON e.id=el.employee_id JOIN leave_types lt ON lt.id=el.leave_type_id WHERE el.entitled=1 ORDER BY e.full_name, lt.name")

elif page == "Cash Advances":
    st.title("Cash Advances")
    st.caption("Cash advance is one official record. Drawer/bank release and payroll deduction link to this record to avoid double counting.")
    tabs = st.tabs(["Cash Advance Ledger", "New Advance", "Drawer Movements", "Repayments"])
    opts = emp_options(True)

    with tabs[0]:
        show_table("Cash Advance Ledger", "SELECT ca.id, e.full_name, ca.request_date, ca.amount, ca.release_method, ca.status, ca.repayment_per_cutoff, ca.custom_next_deduction, ca.outstanding_balance, ca.approved_by, ca.released_by, ca.release_reference, ca.drawer_movement_id FROM cash_advances ca JOIN employees e ON e.id=ca.employee_id ORDER BY ca.request_date DESC")
        actor = st.text_input("Actor for sync", value=current_user, key="ca_sync_actor")
        if st.button("Create Missing Drawer Cash-Out Links"):
            count = create_missing_cash_advance_drawer_movements(conn, actor=actor)
            st.success(f"Created {count} missing drawer movement(s).")
            st.rerun()

    with tabs[1]:
        if opts:
            with st.form("cash_advance"):
                emp_label = st.selectbox("Employee", list(opts.keys()))
                c1, c2, c3 = st.columns(3)
                req_date = c1.date_input("Request Date", value=date.today())
                amount = c2.number_input("Amount", min_value=0.0, step=100.0)
                repay = c3.number_input("Default Deduction per Cutoff", min_value=0.0, step=100.0)
                c4, c5, c6 = st.columns(3)
                method = c4.selectbox("Release Method", ["Cash Drawer", "Bank", "GCash", "Other"])
                status = c5.selectbox("Status", ["Approved", "Released", "Partially Paid", "Fully Paid", "Cancelled"])
                approved_by = c6.text_input("Approved By", value=current_user)
                released_by = st.text_input("Released By", value=current_user if status in ("Released", "Partially Paid") else "")
                ref = st.text_input("Release Reference / Drawer Ref")
                notes = st.text_area("Notes")
                submitted = st.form_submit_button("Save Cash Advance")
                if submitted and amount > 0:
                    cur = execute(conn, "INSERT INTO cash_advances(employee_id, request_date, amount, release_method, release_reference, status, repayment_per_cutoff, outstanding_balance, approved_by, released_by, released_at, notes, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (opts[emp_label], iso(req_date), float(amount), method, ref, status, float(repay), float(amount), approved_by, released_by, now_iso() if status in ("Released", "Partially Paid") else None, notes, now_iso()))
                    ca_id = int(cur.lastrowid)
                    if method == "Cash Drawer" and status in ("Released", "Partially Paid"):
                        movement_id = create_drawer_cash_advance_movement(conn, ca_id, actor=released_by or approved_by or current_user)
                        st.success(f"Cash advance saved and linked to drawer movement #{movement_id}.")
                    else:
                        st.success("Cash advance saved.")
                    st.rerun()

    with tabs[2]:
        st.subheader("Drawer Movements from Staff/Payroll")
        show_table("Drawer Cash-Out / Cash-In Movements", "SELECT movement_date, drawer_name, movement_type, source_type, source_id, amount, method, reference, description, created_by, status, created_at FROM cash_drawer_movements ORDER BY movement_date DESC, id DESC")
        st.info("This is a reconciliation feed only. Final drawer balancing should live in the POS/Accounting drawer module, but the linked record prevents double-counting staff cash advances.")

    with tabs[3]:
        show_table("Cash Advance Repayments", "SELECT car.payment_date, e.full_name, ca.amount AS original_advance, car.amount AS repayment, car.method, car.payroll_run_id, car.notes FROM cash_advance_repayments car JOIN cash_advances ca ON ca.id=car.cash_advance_id JOIN employees e ON e.id=ca.employee_id ORDER BY car.payment_date DESC, car.id DESC")

elif page == "Freelance Outputs":
    st.title("Freelance / Output-Based Pay")
    tabs = st.tabs(["Rate Types", "Weekly Output Entry", "Output History"])
    with tabs[0]:
        with st.form("freelance_rate"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Output Type", placeholder="Pubmat / Video / Reel")
            rate = c2.number_input("Default Rate", min_value=0.0, step=50.0)
            notes = st.text_area("Notes")
            submitted = st.form_submit_button("Save Rate Type")
            if submitted and name:
                execute(conn, "INSERT INTO freelance_rate_types(name, rate, notes) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET rate=excluded.rate, notes=excluded.notes", (name, float(rate), notes))
                st.success("Rate type saved.")
        show_table("Rate Types", "SELECT name, rate, active, notes FROM freelance_rate_types ORDER BY name")
    with tabs[1]:
        opts = emp_options(True)
        rates = fetchall(conn, "SELECT * FROM freelance_rate_types WHERE active=1 ORDER BY name")
        if opts and rates:
            with st.form("freelance_output"):
                emp_label = st.selectbox("Freelancer / Employee", list(opts.keys()))
                start = st.date_input("Week Start", value=date.today() - timedelta(days=date.today().weekday()))
                end = st.date_input("Week End", value=date.today())
                rt_label = st.selectbox("Output Type", [r["name"] for r in rates])
                rt = next(r for r in rates if r["name"] == rt_label)
                qty = st.number_input("Approved Quantity", min_value=0.0, step=1.0)
                rate = st.number_input("Rate", min_value=0.0, value=float(rt["rate"] or 0), step=50.0)
                notes = st.text_area("Notes")
                submitted = st.form_submit_button("Save Approved Outputs")
                if submitted:
                    execute(conn, "INSERT INTO freelance_outputs(employee_id, week_start, week_end, output_type_id, approved_qty, rate, status, notes, created_at) VALUES(?,?,?,?,?,?,?,?,?)", (opts[emp_label], iso(start), iso(end), rt["id"], float(qty), float(rate), "Approved", notes, now_iso()))
                    st.success("Output pay saved.")
    with tabs[2]:
        show_table("Output History", "SELECT fo.week_start, fo.week_end, e.full_name, frt.name AS output_type, fo.approved_qty, fo.rate, (fo.approved_qty*fo.rate) AS payable, fo.status, fo.notes FROM freelance_outputs fo JOIN employees e ON e.id=fo.employee_id JOIN freelance_rate_types frt ON frt.id=fo.output_type_id ORDER BY fo.week_start DESC")

elif page == "Data Import / Templates":
    st.title("Data Import / Templates")
    st.caption("Templates, legacy import, and backup export.")

    tabs = st.tabs(["Required Templates", "Import Filled Template", "Legacy Payroll ZIP Import", "Database Export / Backup", "Import History"])

    with tabs[0]:
        st.subheader("Download required Excel template")
        st.write("The workbook includes sheets for employees, schedules, time logs, leave types, leave entitlements, leave requests, cash advances, freelance rates/outputs, payroll adjustments, holidays, SSS table, and basic biometric import formats.")
        template_bytes = create_required_template_xlsx()
        st.download_button(
            "Download Required Import Template (.xlsx)",
            data=template_bytes,
            file_name="hidden_oasis_staff_payroll_import_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
        st.info("Fill only the sheets you need. The main matching key is employee_code.")

    with tabs[1]:
        st.subheader("Import filled template workbook")
        uploaded = st.file_uploader("Upload completed template (.xlsx)", type=["xlsx", "xls"], key="template_upload")
        actor = st.text_input("Imported by", value="Admin", key="template_actor")
        if uploaded and st.button("Import Template Workbook", type="primary"):
            try:
                result = import_template_xlsx(conn, uploaded.getvalue(), uploaded.name, actor=actor)
                st.success("Template import finished.")
                st.json(result["counts"])
                if result["errors"]:
                    st.warning(f"{len(result['errors'])} row issue(s) found.")
                    st.write(result["errors"][:50])
                st.rerun()
            except Exception as e:
                st.error(f"Import failed: {e}")

    with tabs[2]:
        st.subheader("Import old Payroll.zip / payroll.sqlite")
        st.write("This is for your older uploaded Payroll app data. It can import legacy employees, schedules, time logs, holidays, SSS table, payroll history, line items, other earnings/deductions, and 13th-month records into the new structure.")
        legacy = st.file_uploader("Upload Payroll.zip, a zip containing payroll.sqlite, or a template zip", type=["zip"], key="legacy_zip")
        legacy_actor = st.text_input("Legacy imported by", value="Admin", key="legacy_actor")
        st.warning("Legacy payroll history is imported as Locked so it preserves history without being recomputed. Review migrated data before using it for live payroll.")
        if legacy and st.button("Import Legacy ZIP", type="primary"):
            try:
                result = import_legacy_payroll_zip(conn, legacy.getvalue(), legacy.name, actor=legacy_actor)
                st.success("Legacy import finished.")
                st.json(result["counts"])
                if result["errors"]:
                    st.warning(f"{len(result['errors'])} issue(s) found.")
                    st.write(result["errors"][:80])
                st.rerun()
            except Exception as e:
                st.error(f"Legacy import failed: {e}")

    with tabs[3]:
        st.subheader("Export current database snapshot")
        st.write("Download a full Excel snapshot of major tables for backup/review.")
        snapshot = export_full_database_snapshot_xlsx(conn)
        st.download_button(
            "Download Full Database Snapshot (.xlsx)",
            data=snapshot,
            file_name=f"hidden_oasis_staff_payroll_snapshot_{date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with tabs[4]:
        show_table("Import History", "SELECT file_name, import_type, imported_at, imported_by, row_count, success_count, error_count, notes FROM data_import_batches ORDER BY imported_at DESC, id DESC")

elif page == "Payroll":
    st.title("Payroll")
    tabs = st.tabs(["Compute Draft", "Manual Adjustments", "Payroll Runs", "Payroll Items", "Accounting Queue"])
    with tabs[0]:
        st.subheader("Compute Semi-Monthly Payroll Draft")
        today = date.today()
        default_start = today.replace(day=1 if today.day <= 15 else 16)
        default_end = today.replace(day=15) if today.day <= 15 else (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        c1, c2, c3, c4 = st.columns(4)
        ps = c1.date_input("Period Start", value=default_start)
        pe = c2.date_input("Period End", value=default_end)
        payout = c3.date_input("Payout Date", value=default_end)
        label = c4.text_input("Run Label", value="Regular")
        prepared_by = st.text_input("Prepared by", value=current_user)
        qa_checks = build_payroll_preflight_checks(conn, iso(ps), iso(pe))
        if qa_checks:
            qa_df = pd.DataFrame(qa_checks)
            blockers = qa_df[qa_df["severity"] == "Blocker"]
            with st.expander(f"Payroll QA: {summarize_checks(qa_checks)}", expanded=not blockers.empty):
                st.dataframe(qa_df, use_container_width=True, hide_index=True)
                if not blockers.empty:
                    st.error("Blockers found. You can preview the draft, but do not approve/pay until resolved or deliberately documented.")
        else:
            st.success("Payroll QA found no blockers or warnings for this cutoff.")
        if st.button("Compute Payroll Preview", type="primary"):
            results = compute_payroll(conn, iso(ps), iso(pe))
            st.session_state["payroll_preview"] = [r.as_db_dict() for r in results]
            st.session_state["payroll_params"] = (iso(ps), iso(pe), iso(payout), label, prepared_by)
        if "payroll_preview" in st.session_state:
            df = pd.DataFrame(st.session_state["payroll_preview"])
            display_cols = ["employee_code", "full_name", "regular_hours", "regular_pay", "holiday_pay", "approved_ot_hours", "ot_pay", "night_diff_hours", "night_diff_pay", "paid_leave_pay", "freelance_pay", "other_earnings", "gross_pay", "sss_ee", "philhealth_ee", "pagibig_ee", "tax", "cash_advance_deduction", "other_deductions", "total_deductions", "net_pay", "warnings"]
            st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
            st.metric("Total Net Pay", money(df["net_pay"].sum()))
            if st.button("Save/Replace Draft Payroll"):
                ps0, pe0, payout0, label0, prepared0 = st.session_state["payroll_params"]
                # Recompute from DB to avoid stale session mutation.
                results = compute_payroll(conn, ps0, pe0)
                try:
                    run_id = save_payroll_draft(conn, ps0, pe0, payout0, label0, prepared0, results)
                    st.success(f"Draft payroll saved. Run ID: {run_id}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Payroll draft was not saved: {e}")


    with tabs[1]:
        st.subheader("Manual Payroll Adjustments")
        st.caption("Approved one-off earnings and deductions.")
        opts = emp_options(True)
        if opts:
            with st.form("payroll_adjustment"):
                emp_label = st.selectbox("Employee", list(opts.keys()), key="adj_emp")
                c1, c2, c3 = st.columns(3)
                ps = c1.date_input("Applies From", value=date.today().replace(day=1), key="adj_ps")
                pe = c2.date_input("Applies Until", value=date.today(), key="adj_pe")
                kind = c3.selectbox("Kind", ["Earning", "Deduction"], key="adj_kind")
                c4, c5 = st.columns(2)
                label = c4.text_input("Label", placeholder="Meal allowance / Uniform deduction / Adjustment", key="adj_label")
                amount = c5.number_input("Amount", min_value=0.0, step=50.0, key="adj_amount")
                status = st.selectbox("Status", ["Approved", "Pending", "Rejected", "Cancelled"], key="adj_status")
                notes = st.text_area("Notes", key="adj_notes")
                submitted = st.form_submit_button("Save Adjustment")
                if submitted and label and amount > 0:
                    execute(conn, """
                    INSERT INTO payroll_adjustments(employee_id, period_start, period_end, kind, label, amount, status, notes, created_at)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    """, (opts[emp_label], iso(ps), iso(pe), kind, label, float(amount), status, notes, now_iso()))
                    st.success("Payroll adjustment saved.")
        show_table("Adjustment History", """
        SELECT pa.period_start, pa.period_end, e.full_name, pa.kind, pa.label, pa.amount, pa.status, pa.notes
        FROM payroll_adjustments pa JOIN employees e ON e.id=pa.employee_id
        ORDER BY pa.period_start DESC, e.full_name
        """)


    with tabs[2]:
        runs = df_query("SELECT * FROM payroll_runs ORDER BY period_start DESC, id DESC")
        if runs.empty:
            st.info("No payroll runs yet.")
        else:
            st.dataframe(runs, use_container_width=True, hide_index=True)
            run_id = st.selectbox("Select Run ID", runs["id"].tolist())
            run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (int(run_id),))
            st.write(f"Current status: **{run['status']}**")
            if run.get("validation_summary"):
                st.caption(f"Saved QA summary: {run['validation_summary']}")
            c1, c2, c3, c4, c5 = st.columns(5)
            actor = st.text_input("Actor", value=current_user)
            reason = st.text_input("Reopen/Edit Reason")
            if c1.button("Mark Reviewed"):
                try:
                    update_payroll_status(conn, int(run_id), "Reviewed", actor)
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not mark reviewed: {e}")
            if c2.button("Approve"):
                if not can_review_payroll():
                    st.error("Only Owner/Manager role should approve payroll.")
                else:
                    try:
                        update_payroll_status(conn, int(run_id), "Approved", actor)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not approve payroll: {e}")
            if c3.button("Mark Paid"):
                if not can_review_payroll():
                    st.error("Only Owner/Manager role should mark payroll as paid.")
                else:
                    try:
                        update_payroll_status(conn, int(run_id), "Paid", actor)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not mark payroll paid: {e}")
            if c4.button("Lock"):
                if not can_review_payroll():
                    st.error("Only Owner/Manager role should lock payroll.")
                else:
                    try:
                        update_payroll_status(conn, int(run_id), "Locked", actor)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not lock payroll: {e}")
            if c5.button("Reopen to Draft"):
                if not reason:
                    st.error("Reason is required to reopen payroll.")
                else:
                    try:
                        update_payroll_status(conn, int(run_id), "Draft", actor, reason)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Could not reopen payroll: {e}")

    with tabs[3]:
        show_table("Payroll Items", "SELECT pr.period_start, pr.period_end, pr.status, e.full_name, pi.regular_pay, pi.holiday_pay, pi.ot_pay, pi.night_diff_pay, pi.paid_leave_pay, pi.freelance_pay, pi.other_earnings, pi.gross_pay, pi.sss_ee, pi.philhealth_ee, pi.pagibig_ee, pi.tax, pi.sss_er, pi.sss_ec, pi.philhealth_er, pi.pagibig_er, pi.cash_advance_deduction, pi.other_deductions, pi.net_pay, pi.warnings FROM payroll_items pi JOIN payroll_runs pr ON pr.id=pi.payroll_run_id JOIN employees e ON e.id=pi.employee_id ORDER BY pr.period_start DESC, e.full_name")

    with tabs[4]:
        show_table("Accounting Export Queue", "SELECT source_type, source_id, entry_date, description, debit_account, credit_account, amount, status, created_at FROM accounting_export_queue ORDER BY entry_date DESC, id DESC")

elif page == "Payroll QA":
    st.title("Payroll QA / Preflight Checks")
    st.caption("Review blockers and warnings before payroll approval.")
    today = date.today()
    default_start = today.replace(day=1 if today.day <= 15 else 16)
    default_end = today.replace(day=15) if today.day <= 15 else (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    c1, c2 = st.columns(2)
    ps = c1.date_input("QA Period Start", value=default_start)
    pe = c2.date_input("QA Period End", value=default_end)
    checks = build_payroll_preflight_checks(conn, iso(ps), iso(pe))
    summary = summarize_checks(checks)
    st.metric("QA Summary", summary)
    if checks:
        df = pd.DataFrame(checks)
        st.dataframe(df, use_container_width=True, hide_index=True)
        blockers = df[df["severity"] == "Blocker"]
        if not blockers.empty:
            st.error("There are blockers. Do not approve/pay payroll until these are resolved or intentionally documented.")
        else:
            st.warning("No blockers, but warnings should still be reviewed before final payroll approval.")
    else:
        st.success("No QA blockers or warnings detected for this cutoff.")


elif page == "Accounting Sync":
    st.title("Accounting Sync / Integration Outbox")
    st.caption("Creates idempotent JSON payloads for Accounting. This is an export/review bridge, not silent final posting.")

    tabs = st.tabs(["Create Events", "Outbox", "Export", "Settings"])

    with tabs[0]:
        st.subheader("Create payroll/accounting integration events")
        st.write("Only approved, paid, or locked payroll/13th-month records should be sent to Accounting. Draft payroll stays inside Staff/Payroll.")

        c1, c2, c3 = st.columns(3)
        with c1:
            runs = fetchall(conn, "SELECT id, period_start, period_end, run_label, status FROM payroll_runs WHERE status IN ('Approved','Paid','Locked') ORDER BY id DESC")
            if runs:
                run_options = {f"#{r['id']} {r['period_start']}–{r['period_end']} • {r['run_label']} • {r['status']}": r['id'] for r in runs}
                selected_run = st.selectbox("Payroll run", list(run_options.keys()))
                if st.button("Create Payroll Event"):
                    event_id = enqueue_payroll_run(conn, run_options[selected_run])
                    audit(current_user, "Created payroll integration event", "integration_outbox", event_id, selected_run)
                    st.success(f"Created/updated integration event #{event_id}.")
            else:
                st.info("No approved/paid/locked payroll runs yet.")

        with c2:
            thirteenths = fetchall(conn, "SELECT id, year, period_label, status, net_13th_pay FROM payroll_13th_month_runs WHERE status IN ('Approved','Paid','Locked') ORDER BY id DESC")
            if thirteenths:
                th_options = {f"#{r['id']} {r['year']} • {r['period_label']} • {r['status']} • {money(r['net_13th_pay'])}": r['id'] for r in thirteenths}
                selected_13th = st.selectbox("13th month run", list(th_options.keys()))
                if st.button("Create 13th Month Event"):
                    event_id = enqueue_13th_month(conn, th_options[selected_13th])
                    audit(current_user, "Created 13th month integration event", "integration_outbox", event_id, selected_13th)
                    st.success(f"Created/updated integration event #{event_id}.")
            else:
                st.info("No approved/paid/locked 13th month runs yet.")

        with c3:
            if st.button("Create Employee Sync Event"):
                event_id = enqueue_employee_sync(conn)
                audit(current_user, "Created employee sync integration event", "integration_outbox", event_id, "all employees")
                st.success(f"Created employee sync event #{event_id}.")

        st.divider()
        st.subheader("Cash advance events")
        ca_rows = fetchall(conn, "SELECT ca.id, e.full_name, ca.amount, ca.outstanding_balance, ca.status, ca.release_method FROM cash_advances ca JOIN employees e ON e.id=ca.employee_id WHERE ca.status IN ('Released','Partially Paid','Fully Paid') ORDER BY ca.id DESC")
        if ca_rows:
            ca_options = {f"CA #{r['id']} • {r['full_name']} • {money(r['amount'])} • {r['status']} • {r['release_method']}": r['id'] for r in ca_rows}
            ca_label = st.selectbox("Cash advance release", list(ca_options.keys()))
            if st.button("Create Cash Advance Release Event"):
                event_id = enqueue_cash_advance_release(conn, ca_options[ca_label])
                audit(current_user, "Created cash advance release integration event", "integration_outbox", event_id, ca_label)
                st.success(f"Created/updated integration event #{event_id}.")
        else:
            st.info("No released cash advances yet.")

        repay_rows = fetchall(conn, "SELECT car.id, e.full_name, car.amount, car.payment_date, car.payroll_run_id FROM cash_advance_repayments car JOIN cash_advances ca ON ca.id=car.cash_advance_id JOIN employees e ON e.id=ca.employee_id ORDER BY car.id DESC")
        if repay_rows:
            repay_options = {f"Repay #{r['id']} • {r['full_name']} • {money(r['amount'])} • {r['payment_date']}": r['id'] for r in repay_rows}
            repay_label = st.selectbox("Cash advance repayment", list(repay_options.keys()))
            if st.button("Create Cash Advance Repayment Event"):
                event_id = enqueue_cash_advance_repayment(conn, repay_options[repay_label])
                audit(current_user, "Created cash advance repayment integration event", "integration_outbox", event_id, repay_label)
                st.success(f"Created/updated integration event #{event_id}.")

    with tabs[1]:
        st.subheader("Integration outbox")
        show_table("Events", "SELECT id, event_type, external_id, source_type, source_id, status, attempt_count, last_error, created_at, updated_at, sent_at FROM integration_outbox ORDER BY id DESC")
        ids_text = st.text_input("Event IDs to mark sent/error/ready (comma-separated)")
        ids = [int(x.strip()) for x in ids_text.split(',') if x.strip().isdigit()]
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Mark selected as Sent"):
                mark_outbox_status(conn, ids, "Sent")
                st.success("Updated selected events.")
        with c2:
            if st.button("Mark selected as Ready"):
                mark_outbox_status(conn, ids, "Ready")
                st.success("Updated selected events.")
        with c3:
            err = st.text_input("Error note", key="sync_error_note")
            if st.button("Mark selected as Error"):
                mark_outbox_status(conn, ids, "Error", err)
                st.success("Updated selected events.")

    with tabs[2]:
        st.subheader("Export payloads")
        status_filter = st.selectbox("Export status", ["Ready", "All", "Sent", "Error"])
        zip_bytes = export_outbox_zip(conn, status_filter)
        st.download_button("Download integration payload ZIP", zip_bytes, file_name=f"staff_payroll_integration_{status_filter.lower()}_{date.today().isoformat()}.zip", mime="application/zip")
        st.caption("ZIP remains the fallback bridge. Direct posting sends Ready events to Accounting or Operations review queues, not final ledgers.")
        post_limit = st.number_input("Direct post limit", min_value=1, max_value=100, value=25, step=1)
        accounting_url = get_setting(conn, "accounting_api_base_url", "http://localhost:8000/api")
        operations_url = get_setting(conn, "operations_api_base_url", "http://localhost:8002/api")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Post Ready Events to Accounting"):
                try:
                    result = post_ready_outbox_to_accounting(conn, limit=int(post_limit), base_url=accounting_url)
                    audit(current_user, "Posted ready integration events to Accounting", "integration_outbox", None, json.dumps(result, default=str))
                    if result["failed"]:
                        st.warning(f"Posted {result['sent']} event(s); {result['failed']} failed and were left in Error status.")
                    else:
                        st.success(f"Posted {result['sent']} ready event(s) to Accounting review queues.")
                    if result["results"]:
                        st.json(result)
                except Exception as exc:
                    st.error(f"Could not post to Accounting: {exc}")
        with c2:
            if st.button("Post Ready Events to Operations"):
                try:
                    result = post_ready_outbox_to_operations(conn, limit=int(post_limit), base_url=operations_url)
                    audit(current_user, "Posted ready integration events to Operations", "integration_outbox", None, json.dumps(result, default=str))
                    if result["failed"]:
                        st.warning(f"Posted {result['sent']} event(s); {result['failed']} failed and were left in Error status.")
                    else:
                        st.success(f"Posted {result['sent']} ready event(s) to Operations review cards.")
                    if result["results"]:
                        st.json(result)
                except Exception as exc:
                    st.error(f"Could not post to Operations: {exc}")

    with tabs[3]:
        st.subheader("Connection settings")
        accounting_url = st.text_input("Accounting API base URL", get_setting(conn, "accounting_api_base_url", "http://localhost:8000/api"))
        pos_url = st.text_input("POS API base URL", get_setting(conn, "pos_api_base_url", "http://localhost:8001/api"))
        ops_url = st.text_input("Operations API base URL", get_setting(conn, "operations_api_base_url", "http://localhost:8002/api"))
        integration_key = st.text_input("Integration API key", get_setting(conn, "integration_api_key", ""), type="password")
        if st.button("Save Integration Settings"):
            set_setting(conn, "accounting_api_base_url", accounting_url)
            set_setting(conn, "pos_api_base_url", pos_url)
            set_setting(conn, "operations_api_base_url", ops_url)
            set_setting(conn, "integration_api_key", integration_key)
            audit(current_user, "Updated integration settings", "app_settings", None, f"accounting={accounting_url}; pos={pos_url}; ops={ops_url}; integration_key=updated")
            st.success("Integration settings saved.")


elif page == "Operations Sync":
    st.title("Operations Sync / Manager Dashboard Bridge")
    st.caption("Exports safe status/review events for the Operations Command Center. Operations can review/route decisions, but Staff/Payroll remains the source of truth for payroll and HR records.")

    tabs = st.tabs(["Create Operations Events", "Suggested Dashboard Cards", "Privacy Boundary"])

    with tabs[0]:
        st.subheader("Create cross-app management events")
        st.write("Send safe status cards to Operations.")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Create Operations Snapshot"):
                event_id = enqueue_operations_snapshot(conn)
                audit(current_user, "Created operations snapshot integration event", "integration_outbox", event_id, "staff.operations.snapshot")
                st.success(f"Created Operations snapshot event #{event_id} in the shared Integration Outbox.")
        with c2:
            runs = fetchall(conn, "SELECT id, period_start, period_end, run_label, status FROM payroll_runs WHERE status IN ('Draft','Reviewed','Approved') ORDER BY id DESC")
            if runs:
                run_options = {f"#{r['id']} {r['period_start']}–{r['period_end']} • {r['run_label']} • {r['status']}": r['id'] for r in runs}
                selected_run = st.selectbox("Payroll run for Operations review", list(run_options.keys()))
                if st.button("Create Payroll Ready Card"):
                    event_id = enqueue_payroll_ready_for_operations(conn, run_options[selected_run])
                    audit(current_user, "Created payroll ready Operations event", "integration_outbox", event_id, selected_run)
                    st.success(f"Created Operations payroll review event #{event_id}.")
            else:
                st.info("No draft/review/approved payroll runs yet.")
        with c3:
            emp_rows = employees(True)
            if emp_rows:
                emp_opts = {f"{e['full_name']} • {e.get('department') or 'No dept'} • {e.get('status') or ''}": e['id'] for e in emp_rows}
                emp_label = st.selectbox("Employee status sync", list(emp_opts.keys()))
                if st.button("Create Employee Status Event"):
                    event_id = enqueue_employee_status_for_operations(conn, emp_opts[emp_label])
                    audit(current_user, "Created employee status Operations event", "integration_outbox", event_id, emp_label)
                    st.success(f"Created Operations employee status event #{event_id}.")

        st.info("Operations events are stored in the same Integration Outbox. Use Accounting Sync -> Export to download the JSON ZIP, or post Ready Operations events directly when the Operations API URL is configured.")

    with tabs[1]:
        st.subheader("What Operations should show")
        cards = {
            "Attendance exceptions": fetchone(conn, "SELECT COUNT(*) AS c FROM time_logs WHERE COALESCE(attendance_status,'Pending') IN ('Pending','Disputed','Needs Manager','Needs Review')") or {"c":0},
            "OT pending": fetchone(conn, "SELECT COUNT(*) AS c FROM time_logs WHERE COALESCE(ot_status,'Pending') IN ('Pending','Review') AND COALESCE(detected_ot_hours,0) > 0") or {"c":0},
            "Leave pending": fetchone(conn, "SELECT COUNT(*) AS c FROM leave_requests WHERE status IN ('Pending','Review')") or {"c":0},
            "Cash advance pending": fetchone(conn, "SELECT COUNT(*) AS c FROM cash_advances WHERE status IN ('Requested','Pending','Approved')") or {"c":0},
            "Payroll ready/review": fetchone(conn, "SELECT COUNT(*) AS c FROM payroll_runs WHERE status IN ('Draft','Reviewed','Approved')") or {"c":0},
            "Memo acknowledgment pending": fetchone(conn, "SELECT COUNT(*) AS c FROM memos WHERE status NOT IN ('Acknowledged','Closed','Archived')") or {"c":0},
        }
        cols = st.columns(3)
        for idx, (label, row) in enumerate(cards.items()):
            with cols[idx % 3]:
                st.metric(label, int(row.get('c') or 0))
        st.caption("These are preview counts. The Operations app should receive them as status/review cards, not as copied payroll records.")

    with tabs[2]:
        st.subheader("Privacy and source-of-truth boundary")
        st.markdown("""
        **Allowed in Operations:** employee code/name, department, role, active/inactive status, pending review counts, source record links, safe summaries.  
        **Not allowed in Operations:** salary/rates, government IDs, benefit settings, detailed payroll lines, private HR notes, sensitive infraction details, full annual review contents.

        Operations may create tasks/approvals and route decisions back to Staff/Payroll. Staff/Payroll remains the official source for attendance, leaves, payroll, memos, infractions, annual reviews, and cash advance ledger.
        """)


elif page == "Payslips":
    st.title("Payslips")
    st.caption("Restored from the original payroll app direction: saved payroll items can generate employee payslip PDFs.")
    runs = df_query("SELECT id, period_start, period_end, payout_date, run_label, status FROM payroll_runs ORDER BY period_start DESC, id DESC")
    if runs.empty:
        st.info("No payroll runs yet. Compute and save a draft payroll first.")
    else:
        run_label_map = {f"#{r['id']} • {r['period_start']} to {r['period_end']} • {r['status']}": int(r['id']) for _, r in runs.iterrows()}
        selected_run_label = st.selectbox("Payroll Run", list(run_label_map.keys()))
        run_id = run_label_map[selected_run_label]
        run = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (run_id,))
        items = df_query("""
            SELECT pi.id, e.full_name, e.employee_code, pi.gross_pay, pi.total_deductions, pi.net_pay
            FROM payroll_items pi JOIN employees e ON e.id=pi.employee_id
            WHERE pi.payroll_run_id=?
            ORDER BY e.full_name
        """, (run_id,))
        if items.empty:
            st.warning("This run has no payroll items yet.")
        else:
            st.dataframe(items, use_container_width=True, hide_index=True)

            # Bulk payslip export for the whole payroll run.
            company_name = get_setting(conn, "company_name", "Hidden Oasis")
            company_addr = get_setting(conn, "company_address", "Gingoog City, Misamis Oriental")
            bulk_buf = io.BytesIO()
            with zipfile.ZipFile(bulk_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                summary_df = df_query("""
                    SELECT e.employee_code, e.full_name, pi.regular_hours, pi.regular_pay, pi.holiday_pay,
                           pi.approved_ot_hours, pi.ot_pay, pi.night_diff_hours, pi.night_diff_pay,
                           pi.paid_leave_days, pi.paid_leave_pay, pi.freelance_pay, pi.other_earnings,
                           pi.gross_pay, pi.sss_ee, pi.philhealth_ee, pi.pagibig_ee,
                           pi.sss_er, pi.sss_ec, pi.philhealth_er, pi.pagibig_er,
                           pi.cash_advance_deduction, pi.other_deductions, pi.total_deductions, pi.net_pay, pi.warnings
                    FROM payroll_items pi JOIN employees e ON e.id=pi.employee_id
                    WHERE pi.payroll_run_id=?
                    ORDER BY e.full_name
                """, (run_id,))
                csv_bytes = summary_df.to_csv(index=False).encode("utf-8-sig")
                zf.writestr("payroll_summary.csv", csv_bytes)
                for _, row in items.iterrows():
                    item_full = fetchone(conn, "SELECT * FROM payroll_items WHERE id=?", (int(row["id"]),))
                    emp_full = fetchone(conn, "SELECT * FROM employees WHERE id=?", (item_full["employee_id"],))
                    line_rows = fetchall(conn, "SELECT kind, label, amount, hours, days, quantity, notes FROM payroll_item_lines WHERE payroll_item_id=? ORDER BY sort_order", (int(row["id"]),))
                    pdf_bytes = generate_payslip_pdf(company_name, company_addr, emp_full, run, item_full, line_rows).getvalue()
                    safe_code = str(emp_full["employee_code"]).replace("/", "-")
                    zf.writestr(f"payslips/{safe_code}_{run['period_start']}_{run['period_end']}_payslip.pdf", pdf_bytes)
            bulk_buf.seek(0)
            st.download_button(
                "Download All Payslips + Summary ZIP",
                data=bulk_buf.getvalue(),
                file_name=f"payslips_{run['period_start']}_{run['period_end']}.zip",
                mime="application/zip",
            )

            item_map = {f"{r['full_name']} ({r['employee_code']}) • Net {money(r['net_pay'])}": int(r['id']) for _, r in items.iterrows()}
            selected_item_label = st.selectbox("Employee Payslip", list(item_map.keys()))
            item_id = item_map[selected_item_label]
            item = fetchone(conn, "SELECT * FROM payroll_items WHERE id=?", (item_id,))
            employee = fetchone(conn, "SELECT * FROM employees WHERE id=?", (item["employee_id"],))
            lines = fetchall(conn, "SELECT kind, label, amount, hours, days, quantity, notes FROM payroll_item_lines WHERE payroll_item_id=? ORDER BY sort_order", (item_id,))
            c1, c2, c3 = st.columns(3)
            c1.metric("Gross Pay", money(item["gross_pay"]))
            c2.metric("Deductions", money(item["total_deductions"]))
            c3.metric("Net Pay", money(item["net_pay"]))
            if lines:
                st.subheader("Payslip Lines")
                st.dataframe(pd.DataFrame(lines), use_container_width=True, hide_index=True)
            company_name = get_setting(conn, "company_name", "Hidden Oasis")
            company_addr = get_setting(conn, "company_address", "Gingoog City, Misamis Oriental")
            pdf = generate_payslip_pdf(company_name, company_addr, employee, run, item, lines)
            st.download_button(
                "Download Payslip PDF",
                data=pdf,
                file_name=f"{employee['employee_code']}_{run['period_start']}_{run['period_end']}_payslip.pdf",
                mime="application/pdf",
                type="primary",
            )

elif page == "13th Month Pay":
    st.title("13th Month Pay")
    st.caption("Restored as a separate payroll function. Default basis is regular/basic pay plus paid leave pay from saved payroll history, divided by 12.")
    opts = emp_options(False)
    if not opts:
        st.info("No employees yet.")
    else:
        tabs = st.tabs(["Compute / Save", "History", "Policy Notes"])
        with tabs[0]:
            emp_label = st.selectbox("Employee", list(opts.keys()))
            emp_id = opts[emp_label]
            employee = fetchone(conn, "SELECT * FROM employees WHERE id=?", (emp_id,))
            c1, c2 = st.columns(2)
            year = c1.number_input("Year", min_value=2020, max_value=2100, value=date.today().year, step=1)
            period_label = c2.text_input("Period Label", value=f"13th Month Pay - {int(year)}")
            basis = compute_13th_month_basis(conn, emp_id, int(year))
            base_13th = round(basis / 12.0, 2)
            st.metric("Computed 13th Month Basis", money(basis))
            st.metric("Base 13th Month Pay", money(base_13th))
            st.caption("Basis currently excludes OT, night differential, holiday/rest premiums, other earnings, freelance output pay, and reimbursements.")
            with st.form("save_13th"):
                c3, c4, c5 = st.columns(3)
                manual_adjustment = c3.number_input("Manual Adjustment (+/-)", value=0.0, step=100.0)
                deductions = c4.number_input("Deductions", min_value=0.0, value=0.0, step=100.0)
                status = c5.selectbox("Status", ["Draft", "Reviewed", "Approved", "Paid", "Locked"])
                release_date = st.date_input("Release Date", value=date.today())
                prepared_by = st.text_input("Prepared by", value="Owner/Manager")
                notes = st.text_area("Notes")
                net = round(base_13th + float(manual_adjustment or 0) - float(deductions or 0), 2)
                st.metric("Net 13th Month Pay", money(net))
                submitted = st.form_submit_button("Save / Replace 13th Month Run", type="primary")
                if submitted:
                    run_id = save_13th_month_run(
                        conn,
                        emp_id,
                        int(year),
                        period_label,
                        basis,
                        float(manual_adjustment or 0),
                        float(deductions or 0),
                        status,
                        iso(release_date),
                        prepared_by,
                        notes,
                    )
                    st.success(f"13th month run saved. Run ID: {run_id}")
                    st.rerun()

        with tabs[1]:
            rows = df_query("""
                SELECT r.id, r.year, r.period_label, e.full_name, r.basis_amount, r.base_13th_amount,
                       r.adjustment_amount, r.deductions, r.net_13th_pay, r.status, r.release_date, r.prepared_by, r.notes
                FROM payroll_13th_month_runs r
                JOIN employees e ON e.id=r.employee_id
                ORDER BY r.year DESC, e.full_name
            """)
            if rows.empty:
                st.info("No 13th month runs saved yet.")
            else:
                st.dataframe(rows, use_container_width=True, hide_index=True)
                run_id = st.selectbox("Select 13th Month Run ID", rows["id"].tolist())
                run = fetchone(conn, "SELECT * FROM payroll_13th_month_runs WHERE id=?", (int(run_id),))
                employee = fetchone(conn, "SELECT * FROM employees WHERE id=?", (run["employee_id"],))
                lines = fetchall(conn, "SELECT kind, label, amount, notes FROM payroll_13th_month_lines WHERE run_id=? ORDER BY sort_order", (int(run_id),))
                if lines:
                    st.dataframe(pd.DataFrame(lines), use_container_width=True, hide_index=True)
                company_name = get_setting(conn, "company_name", "Hidden Oasis")
                company_addr = get_setting(conn, "company_address", "Gingoog City, Misamis Oriental")
                pdf = generate_13th_month_pdf(company_name, company_addr, employee, run)
                st.download_button(
                    "Download 13th Month Payslip PDF",
                    data=pdf,
                    file_name=f"{employee['employee_code']}_{run['year']}_13th_month.pdf",
                    mime="application/pdf",
                    type="primary",
                )

        with tabs[2]:
            st.markdown("""
            **Current V3 policy:** 13th month basis is computed from saved payroll history using regular/basic pay plus paid leave pay only, then divided by 12.

            This intentionally excludes OT, night differential, holiday/rest-day premiums, one-off allowances, reimbursements, freelance output pay, and other adjustments unless you manually add them as an adjustment.
            """)


elif page == "Infractions & Memos":
    st.title("Infractions & Memos")
    tabs = st.tabs(["Infractions", "Memos", "Staff Requests"])
    opts = emp_options(True)
    with tabs[0]:
        if opts:
            with st.form("infraction"):
                emp_label = st.selectbox("Employee", list(opts.keys()))
                c1, c2, c3 = st.columns(3)
                inc_date = c1.date_input("Incident Date", value=date.today())
                category = c2.selectbox("Category", ["Late", "Absence", "AWOL", "Missing Time Out", "Guest Complaint", "Policy Violation", "Performance", "Other"])
                severity = c3.selectbox("Severity", ["Note", "Verbal Warning", "Written Warning", "Serious", "Final"])
                desc = st.text_area("Description")
                action = st.text_input("Action Taken")
                created_by = st.text_input("Created By", value="Supervisor")
                submitted = st.form_submit_button("Save Infraction")
                if submitted and desc:
                    execute(conn, "INSERT INTO infractions(employee_id, incident_date, category, severity, description, action_taken, created_by, created_at) VALUES(?,?,?,?,?,?,?,?)", (opts[emp_label], iso(inc_date), category, severity, desc, action, created_by, now_iso()))
                    st.success("Infraction saved.")
        show_table("Infractions", "SELECT i.incident_date, e.full_name, i.category, i.severity, i.description, i.action_taken, i.status, i.created_by FROM infractions i JOIN employees e ON e.id=i.employee_id ORDER BY i.incident_date DESC")
    with tabs[1]:
        if opts:
            with st.form("memo"):
                emp_label = st.selectbox("Employee", list(opts.keys()), key="memo_emp")
                memo_date = st.date_input("Memo Date", value=date.today())
                memo_type = st.selectbox("Memo Type", ["Notice to Explain", "Written Warning", "Reminder", "Commendation", "Suspension Notice", "Other"])
                subject = st.text_input("Subject")
                body = st.text_area("Body")
                status = st.selectbox("Status", ["Draft", "Issued", "Acknowledged", "Archived"])
                issued_by = st.text_input("Issued By", value="Manager")
                submitted = st.form_submit_button("Save Memo")
                if submitted and subject and body:
                    execute(conn, "INSERT INTO memos(employee_id, memo_date, memo_type, subject, body, status, issued_by, created_at) VALUES(?,?,?,?,?,?,?,?)", (opts[emp_label], iso(memo_date), memo_type, subject, body, status, issued_by, now_iso()))
                    st.success("Memo saved.")
        show_table("Memos", "SELECT m.memo_date, e.full_name, m.memo_type, m.subject, m.status, m.issued_by, m.acknowledged_at FROM memos m JOIN employees e ON e.id=m.employee_id ORDER BY m.memo_date DESC")
    with tabs[2]:
        if opts:
            with st.form("staff_request"):
                emp_label = st.selectbox("Employee", list(opts.keys()), key="req_emp")
                request_type = st.selectbox("Request Type", ["Schedule Change", "Time Correction", "Leave", "Cash Advance", "Uniform/Equipment", "Certificate", "Explanation", "Other"])
                subject = st.text_input("Subject")
                details = st.text_area("Details")
                status = st.selectbox("Status", ["Pending", "Approved", "Rejected", "Needs Clarification", "Cancelled", "Archived"])
                submitted = st.form_submit_button("Save Request")
                if submitted and subject:
                    execute(conn, "INSERT INTO staff_requests(employee_id, request_date, request_type, subject, details, status, created_at) VALUES(?,?,?,?,?,?,?)", (opts[emp_label], iso(date.today()), request_type, subject, details, status, now_iso()))
                    st.success("Request saved.")
        show_table("Staff Requests", "SELECT sr.request_date, e.full_name, sr.request_type, sr.subject, sr.status, sr.reviewed_by, sr.decision_notes FROM staff_requests sr JOIN employees e ON e.id=sr.employee_id ORDER BY sr.request_date DESC")

elif page == "Annual Reviews":
    st.title("Annual Reviews")
    st.caption("Annual reviews can now start from an auto-summary of attendance, payroll, leave, infractions, and memo records. Manager/supervisor still decides the final scores.")
    opts = emp_options(True)
    if opts:
        emp_label = st.selectbox("Employee", list(opts.keys()))
        c1, c2 = st.columns(2)
        start = c1.date_input("Review Period Start", value=date.today().replace(month=1, day=1))
        end = c2.date_input("Review Period End", value=date.today())
        auto = build_annual_review_auto_summary(conn, opts[emp_label], iso(start), iso(end))
        with st.expander("Auto Summary from System Data", expanded=True):
            st.text_area("Auto-generated summary", value=auto["summary"], height=260, key="auto_review_summary_display")
            st.caption("Evidence only. Manager judgment decides the review.")
            st.write("Suggested starting scores:", auto["scores"])

        st.markdown("Scores: 1 low, 5 excellent")
        default_scores = auto.get("scores", {})
        with st.form("annual_review"):
            s1, s2, s3, s4, s5 = st.columns(5)
            reliability = s1.slider("Reliability", 1, 5, int(default_scores.get("reliability", 3)))
            punctuality = s2.slider("Punctuality", 1, 5, int(default_scores.get("punctuality", 3)))
            guest = s3.slider("Guest Service", 1, 5, int(default_scores.get("guest_service", 3)))
            teamwork = s4.slider("Teamwork", 1, 5, int(default_scores.get("teamwork", 3)))
            policy = s5.slider("Policy", 1, 5, int(default_scores.get("policy", 3)))
            strengths = st.text_area("Strengths")
            improvement = st.text_area("Improvement Points")
            auto_summary = st.text_area("Saved Auto Summary", value=auto["summary"], height=180)
            recommendation = st.selectbox("Recommendation", ["Continue", "Regularize", "Extend Probation", "Retrain", "Salary Review", "Promote", "Warning", "Terminate", "Other"])
            reviewer = st.text_input("Reviewer", value="Manager")
            submitted = st.form_submit_button("Save Review")
            if submitted:
                execute(
                    conn,
                    """
                    INSERT INTO annual_reviews(employee_id, review_period_start, review_period_end, reliability_score, punctuality_score,
                        guest_service_score, teamwork_score, policy_score, strengths, improvement_points, auto_summary,
                        recommendation, reviewer, created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (opts[emp_label], iso(start), iso(end), reliability, punctuality, guest, teamwork, policy, strengths, improvement, auto_summary, recommendation, reviewer, now_iso())
                )
                st.success("Annual review saved.")
    show_table("Annual Reviews", "SELECT ar.review_period_start, ar.review_period_end, e.full_name, ar.reliability_score, ar.punctuality_score, ar.guest_service_score, ar.teamwork_score, ar.policy_score, ar.recommendation, ar.status, ar.reviewer FROM annual_reviews ar JOIN employees e ON e.id=ar.employee_id ORDER BY ar.review_period_end DESC")

elif page == "Reports":
    st.title("Reports")
    r1, r2 = st.columns(2)
    with r1:
        show_table("Late / Undertime Summary", "SELECT e.full_name, COUNT(*) AS log_count, SUM(CASE WHEN tl.attendance_status='Pending' THEN 1 ELSE 0 END) AS pending_count, SUM(tl.approved_ot_hours) AS approved_ot_hours FROM time_logs tl JOIN employees e ON e.id=tl.employee_id GROUP BY e.full_name ORDER BY e.full_name")
    with r2:
        show_table("Cash Advance Balances", "SELECT e.full_name, SUM(ca.outstanding_balance) AS outstanding FROM cash_advances ca JOIN employees e ON e.id=ca.employee_id WHERE ca.outstanding_balance > 0 GROUP BY e.full_name")
    show_table("Payroll Summary by Run", "SELECT pr.period_start, pr.period_end, pr.status, COUNT(pi.id) AS employees, SUM(pi.gross_pay) AS gross, SUM(pi.total_deductions) AS deductions, SUM(pi.net_pay) AS net FROM payroll_runs pr LEFT JOIN payroll_items pi ON pi.payroll_run_id=pr.id GROUP BY pr.id ORDER BY pr.period_start DESC")

elif page == "Access Control":
    st.title("Access Control / Role Matrix")
    st.caption("Owner-managed users with hashed passwords and Streamlit session login.")
    tabs = st.tabs(["Users", "Password Reset", "Role Matrix", "Permission Notes"])
    with tabs[0]:
        with st.form("add_app_user"):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Display Name")
            role = c2.selectbox("Role", ["Owner", "Manager", "Supervisor", "Reception", "Payroll Clerk", "Viewer"])
            active = c3.checkbox("Active", value=True)
            password = st.text_input("Initial Password", type="password")
            must_change = st.checkbox("Require password change on next sign-in", value=True)
            if st.form_submit_button("Save User") and name:
                if password and len(password) < 8:
                    st.error("Initial password must be at least 8 characters.")
                else:
                    execute(conn, "INSERT INTO app_users(display_name, role, active, created_at) VALUES(?,?,?,?) ON CONFLICT(display_name) DO UPDATE SET role=excluded.role, active=excluded.active", (name, role, int(active), now_iso()))
                    user = fetchone(conn, "SELECT id FROM app_users WHERE display_name=?", (name,))
                    if password and user:
                        set_user_password(conn, int(user["id"]), password, must_change=must_change)
                    audit(current_user, "Saved app user", "app_users", int(user["id"]) if user else None, f"{name} / {role}")
                    st.success("User saved.")
                    st.rerun()
        show_table("App Users", "SELECT display_name, role, active, must_change_password, last_login_at, created_at FROM app_users ORDER BY role, display_name")
    with tabs[1]:
        user_rows = fetchall(conn, "SELECT id, display_name, role FROM app_users ORDER BY display_name")
        if not user_rows:
            st.info("No users found.")
        else:
            user_options = {f"{u['display_name']} • {u['role']}": u["id"] for u in user_rows}
            with st.form("reset_password"):
                selected_user = st.selectbox("User", list(user_options.keys()))
                new_password = st.text_input("New Password", type="password")
                force_change = st.checkbox("Require password change on next sign-in", value=True, key="force_reset_change")
                if st.form_submit_button("Reset Password", type="primary"):
                    if len(new_password) < 8:
                        st.error("Use at least 8 characters.")
                    else:
                        user_id = int(user_options[selected_user])
                        set_user_password(conn, user_id, new_password, must_change=force_change)
                        audit(current_user, "Reset app user password", "app_users", user_id, selected_user)
                        st.success("Password reset.")
    with tabs[2]:
        matrix = pd.DataFrame([
            {"Action": "Clock/time log import", "Reception": "Yes", "Supervisor": "Yes", "Manager": "Yes", "Owner": "Yes"},
            {"Action": "Review attendance exceptions", "Reception": "Simple verification", "Supervisor": "Yes", "Manager": "Yes", "Owner": "Yes"},
            {"Action": "Approve OT", "Reception": "No", "Supervisor": "Yes", "Manager": "Yes", "Owner": "Yes"},
            {"Action": "Approve leave/cash advance", "Reception": "No", "Supervisor": "Recommend", "Manager": "Yes", "Owner": "Yes"},
            {"Action": "Approve/pay/lock payroll", "Reception": "No", "Supervisor": "No", "Manager": "Yes", "Owner": "Yes"},
            {"Action": "Reopen locked payroll", "Reception": "No", "Supervisor": "No", "Manager": "With reason", "Owner": "With reason"},
        ])
        st.dataframe(matrix, use_container_width=True, hide_index=True)
    with tabs[3]:
        st.info("This local Streamlit build now requires login, stores hashed passwords, and restricts pages/actions by role. A future FastAPI/Next.js deployment should still enforce the same policy on backend endpoints.")


elif page == "Settings":
    st.title("Settings")
    tabs = st.tabs(["Payroll Rules", "Holiday Calendar", "SSS Table", "Departments", "Audit Log"])
    with tabs[0]:
        st.subheader("Payroll Rule Settings")
        keys = [
            "standard_daily_paid_hours", "standard_shift_hours", "standard_break_minutes", "night_diff_start", "night_diff_end",
            "night_diff_rate", "ot_rate", "premium_day_ot_rate", "regular_holiday_multiplier", "special_holiday_multiplier",
            "rest_day_multiplier", "regular_holiday_rest_day_multiplier", "special_holiday_rest_day_multiplier",
            "philhealth_rate", "philhealth_floor", "philhealth_ceiling", "pagibig_rate", "pagibig_employer_rate", "pagibig_ceiling",
            "sss_method", "philhealth_basis", "pagibig_basis", "payroll_cash_account",
            "company_name", "company_address", "13th_month_basis"
        ]
        with st.form("settings"):
            values = {k: st.text_input(k, value=get_setting(conn, k, "")) for k in keys}
            submitted = st.form_submit_button("Save Settings")
            if submitted:
                for k, v in values.items():
                    set_setting(conn, k, v)
                st.success("Settings saved.")
        st.info("SSS method is intentionally locked by policy as actual month-to-date gross catch-up unless you deliberately change it.")

    with tabs[1]:
        st.subheader("Holiday Calendar")
        st.caption("Used by payroll to apply regular holiday, special holiday, and rest-day premium multipliers.")
        with st.form("holiday_form"):
            c1, c2, c3 = st.columns(3)
            hdate = c1.date_input("Holiday Date", value=date.today())
            hname = c2.text_input("Holiday Name")
            htype = c3.selectbox("Holiday Type", ["Regular", "Special"])
            notes = st.text_area("Notes", key="holiday_notes")
            if st.form_submit_button("Save Holiday") and hname:
                execute(conn, """
                INSERT INTO holidays(holiday_date, name, holiday_type, active, notes, created_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(holiday_date) DO UPDATE SET name=excluded.name, holiday_type=excluded.holiday_type, active=excluded.active, notes=excluded.notes
                """, (iso(hdate), hname, htype, 1, notes, now_iso()))
                st.success("Holiday saved.")
        show_table("Holiday Calendar", "SELECT holiday_date, name, holiday_type, active, notes FROM holidays ORDER BY holiday_date DESC")

    with tabs[2]:
        st.subheader("SSS Contribution Table")
        st.caption("Starter table is editable/replaceable. The computation uses table lookup, preserving the uploaded app's style.")
        show_table("Active SSS Rows", "SELECT min_comp, max_comp, msc, ee_share, er_share, ec_share, active FROM sss_contribution_table ORDER BY min_comp")
    with tabs[3]:
        with st.form("dept"):
            name = st.text_input("Department Name")
            if st.form_submit_button("Add Department") and name:
                execute(conn, "INSERT OR IGNORE INTO departments(name, active) VALUES(?,1)", (name,))
                st.success("Department saved.")
        show_table("Departments", "SELECT name, active FROM departments ORDER BY name")
    with tabs[4]:
        show_table("Audit Log", "SELECT actor, action, table_name, record_id, details, created_at FROM audit_logs ORDER BY created_at DESC LIMIT 300")
