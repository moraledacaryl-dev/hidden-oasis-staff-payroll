from __future__ import annotations

from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"

OLD = '''    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none; }
        .block-container { max-width: 560px; padding-top: 4rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )
'''

NEW = '''    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] { display: none; }
        .block-container { max-width: 560px; padding-top: 4rem; }

        /* Login page: keep the visible form inside a card even though Streamlit
           widgets cannot truly live inside a raw HTML div wrapper. */
        div[data-testid="stForm"] {
            max-width: 420px;
            margin: 0 auto;
            border: 1px solid #e1e6df;
            border-radius: 0 0 22px 22px;
            padding: 0 30px 30px 30px;
            background: rgba(255,255,255,.96);
            box-shadow: 0 24px 70px rgba(26,38,30,.09);
            border-top: 0;
        }
        .login-card {
            max-width: 420px;
            margin: 8vh auto 0 auto;
            border: 1px solid #e1e6df;
            border-bottom: 0;
            border-radius: 22px 22px 0 0;
            padding: 30px 30px 10px 30px;
            background: rgba(255,255,255,.96);
            box-shadow: 0 24px 70px rgba(26,38,30,.09);
        }
        .login-credit {
            max-width: 420px;
            margin: 0 auto;
            border: 1px solid #e1e6df;
            border-top: 0;
            border-radius: 0 0 22px 22px;
            padding: 0 30px 22px 30px;
            background: rgba(255,255,255,.96);
            color: #7b8179;
            font-size: 0.8rem;
        }
        .login-card + div[data-testid="stForm"] {
            margin-top: 0 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
'''

OLD_END = '    st.markdown("<div class=\'login-credit\'>by C.M.</div></div></div>", unsafe_allow_html=True)\n'
NEW_END = '    st.markdown("<div class=\'login-credit\'>by C.M.</div>", unsafe_allow_html=True)\n'


def main() -> None:
    s = APP_PATH.read_text(encoding="utf-8")
    if OLD not in s:
        raise SystemExit("Could not find login CSS block. app.py may have changed.")
    s = s.replace(OLD, NEW, 1)
    s = s.replace(OLD_END, NEW_END, 1)
    APP_PATH.write_text(s, encoding="utf-8")
    print("Patched login page so the Streamlit form keeps the card aesthetic.")


if __name__ == "__main__":
    main()
