from datetime import datetime, timedelta
import os
from pathlib import Path
import sys
import pandas as pd
import streamlit as st
from supabase import create_client

# Setzt das Hauptverzeichnis fest in den Suchpfad von Python
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
  sys.path.append(str(root_dir))

st.set_page_config(
    layout="wide",
    page_title="VisionDZ - Leopold Kommandozentrale",
    page_icon="⚙️",
)

if not st.session_state.get("password_correct", False):
  st.warning("Bitte melde dich zuerst auf der Hauptseite an.")
  st.stop()

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

st.title("⚙️ Leopold - Signals Journal & Deep Analytics")
st.markdown("Vollständige Auswertung und detaillierte Kennzahlen des `signals_journal`.")
st.divider()

# Daten aus signals_journal laden
sj_data = []
load_error = None
try:
    res = supabase.table("signals_journal").select("*").execute()
    sj_data = res.data if res and res.data else []
except Exception as e:
    load_error = str(e)

# Diagnose-Hinweis, falls ein Fehler auftrat oder keine Daten da sind
if load_error:
    st.error(f"⚠️ Supabase-Fehler beim Zugriff auf `signals_journal`: {load_error}")
elif not sj_data:
    st.warning(
        "⚠️ Die Tabelle `signals_journal` ist aktuell **leer**. "
        "Es konnten keine Datensätze geladen werden."
    )
else:
    df_sj = pd.DataFrame(sj_data)

    # Spalten-Erkennung für den Typ absichern
    possible_type_cols = ["signal_typ", "typ", "signal_type", "type"]
    type_col = next((c for c in possible_type_cols if c in df_sj.columns), None)

    # Filter-Optionen in der UI (Nur nach Signal-Typ)
    col_f1 = st.columns(1)[0]
    with col_f1:
        if type_col:
            unique_types = ["Alle"] + list(df_sj[type_col].dropna().unique())
            sel_type = st.selectbox("Nach Signal-Typ filtern", unique_types, key="leopold_type_filter")
        else:
            sel_type = "Alle"
            st.info("ℹ️ Keine Signal-Typ-Spalte gefunden ('signal_typ' oder ähnlich). Filter wird übersprungen.")

    # DataFrame nach Filter verfeinern
    df_filtered = df_sj.copy()
    if type_col and sel_type != "Alle":
        df_filtered = df_filtered[df_filtered[type_col] == sel_type]

    # Teilmengen für Elite vs. Kauf bestimmen (falls Spalte existiert)
    if type_col:
        df_elite = df_sj[df_sj[type_col].astype(str).str.lower().str.contains("elite", na=False)]
        df_kauf = df_sj[df_sj[type_col].astype(str).str.lower().str.contains("kauf|buy", na=False)]
    else:
        df_elite = pd.DataFrame()
        df_kauf = pd.DataFrame()

    # Hilfsfunktion für sichere Mittelwert-Berechnung
    def safe_mean(dataframe, column_name):
        if not dataframe.empty and column_name in dataframe.columns:
            val = pd.to_numeric(dataframe[column_name], errors='coerce').mean()
            return val if pd.notnull(val) else 0.0
        return 0.0

    # KPI 1: Performance Elite & Kaufsignale
    perf_target_col = next((c for c in ["end_performance_5_tage", "performance", "end_performance"] if c in df_sj.columns), None)
    perf_elite = safe_mean(df_elite, perf_target_col)
    perf_kauf = safe_mean(df_kauf, perf_target_col)

    # KPI 2: Gewinntrades Quote (%)
    win_rate = 0.0
    if not df_filtered.empty and perf_target_col:
        numeric_perf = pd.to_numeric(df_filtered[perf_target_col], errors='coerce')
        winning_trades = (numeric_perf > 0).sum()
        total_valid_trades = numeric_perf.dropna().count()
        if total_valid_trades > 0:
            win_rate = (winning_trades / total_valid_trades) * 100

    # KPI 3: Durchschnittliche Tage bis Max Performance
    days_col = next((c for c in ["tage_bis_max_perf", "days_to_max", "max_perf_tage", "tage_bis_max"] if c in df_filtered.columns), None)
    avg_days_to_max = safe_mean(df_filtered, days_col)

    # KPI 4: 5 Tage End & Max Werte für Elite & Kauf
    elite_5d_end = safe_mean(df_elite, "end_performance_5_tage")
    elite_5d_max = safe_mean(df_elite, "max_performance_5_tage")
    kauf_5d_end = safe_mean(df_kauf, "end_performance_5_tage")
    kauf_5d_max = safe_mean(df_kauf, "max_performance_5_tage")

    # --- ANZEIGE DER KPI METRIKEN ---
    st.markdown("### 📊 Performance-Kennzahlen")
    
    r1_c1, r1_c2, r1_c3, r1_c4 = st.columns(4)
    with r1_c1:
        st.metric("Performance Elite-Signale", f"{perf_elite:+.2f}%")
    with r1_c2:
        st.metric("Performance Kaufsignale", f"{perf_kauf:+.2f}%")
    with r1_c3:
        st.metric("Gewinntrades (Quote)", f"{win_rate:.1f}%")
    with r1_c4:
        st.metric("Ø Tage bis Max-Perf.", f"{avg_days_to_max:.1f} Tage")

    r2_c1, r2_c2, r2_c3, r2_c4 = st.columns(4)
    with r2_c1:
        st.metric("5T End (Elite)", f"{elite_5d_end:+.2f}%")
    with r2_c2:
        st.metric("5T Max (Elite)", f"{elite_5d_max:+.2f}%")
    with r2_c3:
        st.metric("5T End (Kauf)", f"{kauf_5d_end:+.2f}%")
    with r2_c4:
        st.metric("5T Max (Kauf)", f"{kauf_5d_max:+.2f}%")

    st.divider()

    # --- KOMPLETTES JOURNAL ALS TABELLE ---
    st.subheader(f"📋 Komplettes Signals Journal ({len(df_filtered)} Einträge)")
    st.dataframe(df_filtered, use_container_width=True, hide_index=True)

    # Download-Button als CSV
    csv_data = df_filtered.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Signals Journal als CSV herunterladen",
        data=csv_data,
        file_name="signals_journal_complete_export.csv",
        mime="text/csv",
    )