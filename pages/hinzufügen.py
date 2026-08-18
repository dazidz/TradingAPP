import streamlit as st
from supabase import create_client

# Seitentitel für die mobile Ansicht
st.title("➕ Ticker hinzufügen")
st.markdown("Füge schnell neue Aktien von unterwegs zu deiner Watchlist hinzu.")

# Verbindung zu Supabase
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

with st.form("add_ticker_form", clear_on_submit=True):
    ticker_input = st.text_input("Ticker-Symbol (z.B. AAPL)").upper()
    company_name = st.text_input("Unternehmensname")
    sector = st.text_input("Sektor (optional)")
    notes = st.text_area("Notizen / Grund für das Interesse (optional)")
    
    # Großer Button, perfekt für den Daumen am Handy
    submitted = st.form_submit_button("💾 Zur Watchlist hinzufügen", use_container_width=True)
    
    if submitted:
        if ticker_input and company_name:
            try:
                data = {
                    "ticker": ticker_input,
                    "company_name": company_name,
                    "sector": sector if sector else "Unbekannt",
                    "notes": notes,
                    "status": "watchlist"
                }
                
                # Schreibt die Daten in deine 'watchlist' Tabelle in Supabase
                response = supabase.table("watchlist").insert(data).execute()
                
                st.success(f"Erfolgreich gespeichert: **{company_name}** ({ticker_input})!")
            except Exception as e:
                st.error(f"Fehler beim Speichern in Supabase: {e}")
        else:
            st.warning("Bitte fülle mindestens das **Ticker-Symbol** und den **Unternehmensnamen** aus.")