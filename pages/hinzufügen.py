import streamlit as st
from supabase import create_client

# Sicherheits-Check: Nur Zugriff, wenn bereits auf der Hauptseite eingeloggt
if "password_correct" not in st.session_state or not st.session_state.password_correct:
    st.error("Bitte zuerst auf der Startseite anmelden!")
    st.stop()

# --- SEITENINHALT ---
st.title("➕ Ticker hinzufügen")
st.markdown("Füge schnell neue Aktien von unterwegs zu deiner Watchlist hinzu.")

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

with st.form("add_ticker_form", clear_on_submit=True):
    ticker_input = st.text_input("Ticker-Symbol (z.B. AAPL)").upper()
    
    # Eingabe für den Gettex-Ticker (ohne 'gettex:' davor)
    gettex_raw = st.text_input("Gettex Ticker (z.B. SAP)").upper()
    
    company_name = st.text_input("Unternehmensname")
    sector = st.text_input("Sektor (optional)")
    
    submitted = st.form_submit_button("💾 Zur Watchlist hinzufügen", use_container_width=True)
    
    if submitted:
        if ticker_input and company_name:
            try:
                # Automatisches Voranstellen von 'gettex:', falls etwas eingegeben wurde
                gettex_ticker_final = f"gettex:{gettex_raw}" if gettex_raw else None
                
                data = {
                    "ticker": ticker_input,
                    "gettex_ticker": gettex_ticker_final,
                    "company_name": company_name,
                    "sector": sector if sector else None
                }
                
                supabase.table("watchlist").insert(data).execute()
                st.success(f"Erfolgreich gespeichert: **{company_name}** ({ticker_input})!")
            except Exception as e:
                st.error(f"Fehler beim Speichern in Supabase: {e}")
        else:
            st.warning("Bitte fülle mindestens das **Ticker-Symbol** und den **Unternehmensnamen** aus.")