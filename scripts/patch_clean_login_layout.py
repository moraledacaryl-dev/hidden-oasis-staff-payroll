from __future__ import annotations

from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"

OLD_CSS_BLOCK = '''    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none; }
        .block-container { max-width: 560px; padding-top: 4rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )
'''

NEW_CSS_BLOCK = '''    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none; }
        .block-container { max-width: 560px; padding-top: 4rem; }

        .login-shell {
            max-width: 420px;
            margin: 8vh auto 0 auto;
            border: 1px solid #e1e6df;
            border-radius: 22px;
            padding: 30px;
            background: rgba(255,255,255,.96);
            box-shadow: 0 24px 70px rgba(26,38,30,.09);
        }
        .login-shell .login-credit {
            color: #7b8179;
            font-size: 0.8rem;
            margin-top: 1rem;
        }
        .login-shell + div[data-testid="stForm"] {
            max-width: 420px;
            margin: -1px auto 0 auto;
            border: 1px solid #e1e6df;
            border-top: 0;
            border-radius: 0 0 22px 22px;
            padding: 0 30px 30px 30px;
            background: rgba(255,255,255,.96);
            box-shadow: 0 24px 70px rgba(26,38,30,.09);
        }
        div[data-testid="stForm"] {
            max-width: 420px;
            margin-left: auto;
            margin-right: auto;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
'''

OLD_HEADER = '''    st.markdown("<div class='login-view'>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class="login-card">
            <div class="login-mark">HO</div>
            <div class="login-title">Staff & Payroll</div>
        """,
        unsafe_allow_html=True,
    )
'''

NEW_HEADER = '''    st.markdown(
        """
        <div class="login-shell">
            <div class="login-mark">HO</div>
            <div class="login-title">Staff & Payroll</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
'''

OLD_FOOTER = '''    st.markdown("<div class='login-credit'>by C.M.</div></div></div>", unsafe_allow_html=True)
'''

NEW_FOOTER = '''    st.markdown("<div class='login-shell' style='margin-top:0;border-top:0;border-radius:0 0 22px 22px;padding-top:0;box-shadow:none;'><div class='login-credit'>by C.M.</div></div>", unsafe_allow_html=True)
'''


def main() -> None:
    text = APP_PATH.read_text(encoding="utf-8")

    if OLD_CSS_BLOCK not in text:
        raise SystemExit("Could not find login CSS block. Stop: app.py differs from expected file.")
    text = text.replace(OLD_CSS_BLOCK, NEW_CSS_BLOCK, 1)

    if OLD_HEADER not in text:
        raise SystemExit("Could not find login header raw HTML block. Stop: app.py differs from expected file.")
    text = text.replace(OLD_HEADER, NEW_HEADER, 1)

    if OLD_FOOTER not in text:
        raise SystemExit("Could not find login footer raw HTML block. Stop: app.py differs from expected file.")
    text = text.replace(OLD_FOOTER, NEW_FOOTER, 1)

    # Safety check: no login-view wrapper should remain open/closed in the login branch.
    if "<div class='login-view'>" in text or "</div></div>" in text[text.find('if st.session_state["auth_user"] is None:'):text.find('st.stop()', text.find('if st.session_state["auth_user"] is None:'))]:
        raise SystemExit("Login branch still has suspicious wrapper HTML after patch; not writing file.")

    APP_PATH.write_text(text, encoding="utf-8")
    print("Cleaned login layout: removed broken wrapper nesting and restored a card-style login.")


if __name__ == "__main__":
    main()
