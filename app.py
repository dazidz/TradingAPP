import streamlit as st

st.set_page_config(layout="wide", page_title="Trading Dashboard")

def check_password():
    if "password_correct" not in st.session_state: st.session_state.password_correct = False
    if not st.session_state.password_correct:
        st.title("🔐 Bitte anmelden")
        input_pw = st.text_input("Passwort:", type="password")
        if st.button("Anmelden", use_container_width=True):
            if input_pw == st.secrets["APP_PASSWORD"]:
                st.session_state.password_correct = True
                st.rerun()
            else: st.error("Passwort falsch.")
        return False
    return True

if check_password():
    st.title("📈 Trading Dashboard")
    st.write("Willkommen! Hier ist dein zentraler Überblick.")
    
    col1, col2, col3 = st.columns(3)
    with col1: st.metric(label="S&P 500", value="--", delta="--")
    with col2: st.metric(label="Nasdaq 100", value="--", delta="--")
    with col3: st.metric(label="DAX", value="--", delta="--")
    
    st.info("👈 Nutze die Seitenleiste für den Screener, die Watchlist und das Journal.")