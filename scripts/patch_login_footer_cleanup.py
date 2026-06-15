from pathlib import Path
p = Path(__file__).resolve().parents[1] / 'app.py'
s = p.read_text()
s = s.replace("    st.markdown(\"<div class='login-credit'>by C.M.</div></div></div>\", unsafe_allow_html=True)\n", "    st.markdown(\"<div class='login-credit'>by C.M.</div>\", unsafe_allow_html=True)\n")
s = s.replace("    st.markdown(\"<div class='login-view'>\", unsafe_allow_html=True)\n", "")
p.write_text(s)
print('Cleaned login footer wrapper.')
