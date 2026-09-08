from pathlib import Path
import sys
import pandas as pd
import streamlit as st
from supabase import create_client

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
  sys.path.append(str(root_dir))

from services.fair_value_screener import FairValueScreener

st.set_page_config(
    layout="wide",
    page_title="VisionDZ - Fair Value Screener",
    page_icon="📐",
)

if not st.session_state.get("password_correct", False):
  st.warning("Bitte melde dich zuerst auf der Hauptseite an.")
  st.stop()

try:
  URL = st.secrets["SUPABASE_URL"]
  KEY = st.secrets["SUPABASE_KEY"]
  supabase = create_client(URL, KEY)
except Exception as e:
  st.error(f"Fehler beim Verbinden mit Supabase: {e}")
  st.stop()

st.title("📐 Autonomer Fair Value Screener")
st.markdown(
    "Tagesaktuelle Bewertung des inneren Wertes (Multi-Modell Blend aus KGV,"
    " Buchwert und Free Cash Flow) für alle Watchlist-Titel."
)

screener = FairValueScreener(supabase)

# Automatisches Laden aus dem Cache (einmal am Tag / Tagesstand)
col1, col2 = st.columns([3, 1])
with col2:
  force_refresh = st.button("🔄 Tagesstand neu berechnen", use_container_width=True)

st.divider()

with st.spinner("Lade Fair-Value-Daten..."):
  df, was_refreshed = screener.get_or_calculate_fair_values(
      force_refresh=force_refresh
  )

if was_refreshed:
  st.toast("Tagesaktuelle Fair Values wurden neu berechnet und gespeichert!", icon="🔄")

if not df.empty:
  # Filter-Optionen
  col_f1, col_f2 = st.columns(2)
  with col_f1:
    status_filter = st.multiselect(
        "Nach Status filtern:",
        options=df["Status"].unique().tolist(),
        default=df["Status"].unique().tolist(),
    )

  filtered_df = df[df["Status"].isin(status_filter)]

  st.markdown("### 📊 Bewertungsübersicht")
  st.dataframe(filtered_df, use_container_width=True, hide_index=True)

  st.markdown("### 🚀 Top Unterbewertete Chancen (Margin of Safety)")
  undervalued = df[df["Status"].str.contains("Stark Unterbewertet", na=False)]
  if not undervalued.empty:
    for _, row in undervalued.iterrows():
      st.success(
          f"**{row['Ticker']} ({row['Name']})** | Sektor: {row['Sektor']} |"
          f" Aktuell: **${row['Aktueller Preis']}** | Fair Value: **$"
          f" {row['Fair Value (Est.)']}** | Potential: **{row['Potential (%)']}"
          "**"
      )
  else:
    st.info(
        "Aktuell befinden sich keine Titel mit 'Stark Unterbewertet' auf der"
        " Watchlist."
    )
else:
  st.warning(
      "Keine Daten im Fair-Value-Cache gefunden oder Watchlist ist leer."
  )