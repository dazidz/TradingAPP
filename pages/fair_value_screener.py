import sys
from pathlib import Path
import pandas as pd
import streamlit as st
from supabase import create_client

# Pfad anpassen, damit Module aus dem Hauptverzeichnis geladen werden können
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

# Supabase Verbindung
try:
  URL = st.secrets["SUPABASE_URL"]
  KEY = st.secrets["SUPABASE_KEY"]
  supabase = create_client(URL, KEY)
except Exception as e:
  st.error(f"Fehler beim Verbinden mit Supabase: {e}")
  st.stop()

st.title("📐 Autonomer Fair Value Screener")
st.markdown(
    "Ermittlung des inneren Wertes (Multi-Modell Blend aus KGV, Buchwert und"
    " Free Cash Flow) für alle Watchlist-Titel – angelehnt an institutionelle"
    " Bewertungsmodelle."
)

screener = FairValueScreener(supabase)

col1, col2 = st.columns([1, 4])
with col1:
  run_button = st.button(
      "🔄 Fair Values berechnen", type="primary", use_container_width=True
  )

st.divider()

# Cache oder Live-Berechnung bei Klick
if "fv_df" not in st.session_state:
  st.session_state.fv_df = pd.DataFrame()

if run_button:
  with st.spinner(
      "Analysiere Bilanzen, Cashflows und berechne faire Werte..."
  ):
    st.session_state.fv_df = screener.calculate_fair_value_batch()

if not st.session_state.fv_df.empty:
  df = st.session_state.fv_df

  # Filter-Optionen in der Sidebar oder direkt oben
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

  # Visuelle Hervorhebung der Top-Chancen (Stark unterbewertet)
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
  st.info(
      "Klicke oben auf **'Fair Values berechnen'**, um den Screener zu"
      " starten."
  )