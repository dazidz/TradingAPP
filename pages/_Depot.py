from datetime import datetime
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(
    layout="wide",
    page_title="VisionDZ - Investing & Trading Depot",
    page_icon="💼",
)

if not st.session_state.get("password_correct", False):
    st.warning("Bitte melde dich zuerst auf der Hauptseite an.")
    st.stop()

# Supabase Verbindung
try:
    URL = st.secrets["SUPABASE_URL"]
    KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(URL, KEY)
except Exception as e:
    st.error(f"Fehler beim Verbinden mit Supabase: {e}")
    st.stop()

st.title("💼 Depot-Management & Trading-Zentrale")
st.markdown("Verwalte deine Depots, das Trading Journal und überwache die Fair-Value-Bewertungen.")

st.divider()

# Hilfsfunktion zum Laden des Fair-Value-Caches
@st.cache_data(ttl=60)
def load_fair_value_cache():
    try:
        res = supabase.table("fair_value_cache").select("*").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            df.columns = [str(c).lower() for c in df.columns]
            return df
    except Exception:
        pass
    return pd.DataFrame()

df_cache = load_fair_value_cache()
# Nur relevante Cache-Spalten behalten
if not df_cache.empty:
    cache_cols = ["ticker", "fair_value", "potential_pct", "status", "eps", "fcf_aktie"]
    df_cache_filtered = df_cache[[c for c in cache_cols if c in df_cache.columns]]
else:
    df_cache_filtered = pd.DataFrame(columns=["ticker"])

# Haupt-Navigation über Tabs (Struktur wiederhergestellt!)
tab_depots, tab_journal, tab_actions = st.tabs([
    "📊 Depots & Positionen", 
    "📓 Trading Journal", 
    "⚙️ Position öffnen / schließen"
])

# ==========================================
# TAB 1: DEPOTS & POSITIONEN
# ==========================================
with tab_depots:
    st.subheader("Aktive Depots")
    
    # Unter-Tabs für verschiedene Depots (z.B. Risk Depot, Core, Swing)
    sub_tab1, sub_tab2 = st.tabs(["Risk Depot", "Core / Swing Depot"])
    
    with sub_tab1:
        st.markdown("### 🔴 Risk Depot")
        try:
            res_risk = supabase.table("risk_depot").select("*").execute()
            df_risk = pd.DataFrame(res_risk.data) if res_risk.data else pd.DataFrame()
            
            if not df_risk.empty:
                df_risk.columns = [str(c).lower() for c in df_risk.columns]
                # Merge mit Fair Value Cache
                df_risk_merged = pd.merge(df_risk, df_cache_filtered, on="ticker", how="left")
                
                st.dataframe(
                    df_risk_merged,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "fair_value": st.column_config.NumberColumn("Fair Value", format="€ %.2f"),
                        "potential_pct": st.column_config.NumberColumn("Potenzial", format="%.1f %%"),
                        "status": st.column_config.TextColumn("Bewertung"),
                        "aktueller_preis": st.column_config.NumberColumn("Kurs", format="€ %.2f"),
                    }
                )
            else:
                st.info("Keine Positionen im Risk Depot gefunden.")
        except Exception as e:
            st.error(f"Fehler beim Laden des Risk Depots: {e}")

    with sub_tab2:
        st.markdown("### 🟢 Core & Swing Depot")
        try:
            # Falls du hier eine andere Tabelle hast (z.B. "watchlist" oder "depot"), anpassen:
            res_core = supabase.table("watchlist").select("*").execute() # Beispielhaft, falls Core dort liegt
            df_core = pd.DataFrame(res_core.data) if res_core.data else pd.DataFrame()
            
            if not df_core.empty:
                df_core.columns = [str(c).lower() for c in df_core.columns]
                df_core_merged = pd.merge(df_core, df_cache_filtered, on="ticker", how="left")
                
                st.dataframe(
                    df_core_merged,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "fair_value": st.column_config.NumberColumn("Fair Value", format="€ %.2f"),
                        "potential_pct": st.column_config.NumberColumn("Potenzial", format="%.1f %%"),
                        "status": st.column_config.TextColumn("Bewertung"),
                    }
                )
            else:
                st.info("Keine Positionen im Core Depot gefunden.")
        except Exception as e:
            st.info("Keine zusätzlichen Depot-Daten geladen.")

# ==========================================
# TAB 2: TRADING JOURNAL
# ==========================================
with tab_journal:
    st.subheader("📓 Trading Journal & Historie")
    try:
        res_journal = supabase.table("trading_journal").select("*").execute()
        df_journal = pd.DataFrame(res_journal.data) if res_journal.data else pd.DataFrame()
        
        if not df_journal.empty:
            st.dataframe(df_journal, use_container_width=True, hide_index=True)
        else:
            st.info("Noch keine Einträge im Trading Journal vorhanden.")
    except Exception as e:
        st.warning(f"Trading-Journal-Tabelle konnte nicht geladen werden: {e}")

# ==========================================
# TAB 3: POSITION ÖFFNEN / SCHLIESSEN
# ==========================================
with tab_actions:
    st.subheader("⚙️ Positions-Management")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### ➕ Position öffnen")
        with st.form("form_open_pos"):
            open_ticker = st.text_input("Ticker / Symbol").upper()
            open_depot = st.selectbox("Ziel-Depot", ["risk_depot", "core_depot"])
            open_shares = st.number_input("Anzahl Aktien", min_value=0.0, value=1.0)
            open_price = st.number_input("Kaufpreis (€)", min_value=0.0, value=10.0)
            
            submitted_open = st.form_submit_button("Position eröffnen")
            if submitted_open and open_ticker:
                try:
                    supabase.table(open_depot).insert({
                        "ticker": open_ticker,
                        "shares": open_shares,
                        "entry_price": open_price,
                        "date_opened": datetime.now().isoformat()
                    }).execute()
                    st.success(f"Position für {open_ticker} erfolgreich im {open_depot} eröffnet!")
                except Exception as e:
                    st.error(f"Fehler beim Öffnen der Position: {e}")

    with col2:
        st.markdown("#### ❌ Position schließen")
        with st.form("form_close_pos"):
            close_ticker = st.text_input("Zu schließender Ticker").upper()
            close_depot = st.selectbox("Aus Depot entfernen", ["risk_depot", "core_depot"])
            
            submitted_close = st.form_submit_button("Position schließen")
            if submitted_close and close_ticker:
                try:
                    supabase.table(close_depot).delete().eq("ticker", close_ticker).execute()
                    st.success(f"Position für {close_ticker} aus {close_depot} entfernt / geschlossen!")
                except Exception as e:
                    st.error(f"Fehler beim Schließen der Position: {e}")