from datetime import datetime
import json
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


def render_leopold_signals_dashboard(supabase_client):
  """Rendert das neue Leopold-Dashboard für das gesamte signals_journal

  inklusive Tabellenansicht und detaillierter Performance-Auswertungen.
  """
  st.subheader("📊 Leopold Signals Dashboard & Analytics")

  # 1. Daten aus signals_journal laden
  try:
    response = (
        supabase_client.table("signals_journal").select("*").execute()
    )
    data = response.data
    if not data:
      st.info(
          "Keine Einträge im `signals_journal` gefunden. Das Journal wird von"
          " Nino befüllt."
      )
      return
    df = pd.DataFrame(data)
  except Exception as e:
    st.error(f"Fehler beim Laden des `signals_journal`: {e}")
    return

  # Hilfsspalten / Formatierungen sicherstellen
  if "signal_datum" in df.columns:
    df["signal_datum"] = pd.to_datetime(
        df["signal_datum"], errors="coerce"
    ).dt.date

  # -------------------------------------------------------------------------
  # METRIKEN & BERECHNUNGEN (KPI-Bereich)
  # -------------------------------------------------------------------------

  # Erkennung von Elite- vs. Kaufsignalen über signal_typ (Fallback auf 'Standard')
  df["signal_typ_clean"] = (
      df["signal_typ"].fillna("Standard").astype(str).str.lower()
  )
  is_elite = df["signal_typ_clean"].str.contains("elite", na=False)
  is_kauf = df["signal_typ_clean"].str.contains(
      "kauf|buy|standard", na=False
  ) & ~is_elite

  # Datensätze filtern für spezielle Analysen
  df_elite = df[is_elite]
  df_kauf = df[is_kauf]

  # Gewinntrades (anhand der 30D-Performance oder 5D-Performance, falls 30D fehlt)
  perf_col_30d = (
      "performance_30d_end_pct"
      if "performance_30d_end_pct" in df.columns
      else "end_performance_5_tage"
  )
  if perf_col_30d in df.columns:
    total_wins = df[df[perf_col_30d] > 0].shape[0]
    total_evaluated = df[df[perf_col_30d].notnull()].shape[0]
    win_rate = (
        round((total_wins / total_evaluated) * 100, 1)
        if total_evaluated > 0
        else 0.0
    )
  else:
    win_rate, total_wins = 0.0, 0

  # Performance-Berechnungen (Mittelwerte)
  def safe_mean(series):
    if series.empty or series.dropna().empty:
        return 0.0
    return round(float(series.dropna().mean()), 2)

  # 1. Performance Elite Signale (Gesamt / 30D End oder bestverfügbar)
  perf_elite = safe_mean(df_elite[perf_col_30d]) if not df_elite.empty else 0.0

  # 2. Performance Kaufsignale
  perf_kauf = safe_mean(df_kauf[perf_col_30d]) if not df_kauf.empty else 0.0

  # 3. 5 Tage Metriken
  perf_5d_end_elite = (
      safe_mean(df_elite["end_performance_5_tage"])
      if "end_performance_5_tage" in df_elite.columns
      else 0.0
  )
  perf_5d_max_elite = (
      safe_mean(df_elite["max_performance_5_tage"])
      if "max_performance_5_tage" in df_elite.columns
      else 0.0
  )

  perf_5d_end_kauf = (
      safe_mean(df_kauf["end_performance_5_tage"])
      if "end_performance_5_tage" in df_kauf.columns
      else 0.0
  )
  perf_5d_max_kauf = (
      safe_mean(df_kauf["max_performance_5_tage"])
      if "max_performance_5_tage" in df_kauf.columns
      else 0.0
  )

  # 4. Durchschnittliche Tage bis Max-Perf (falls candle_time_max_5_tage & signal_datum vorhanden)
  avg_days_to_max = 0.0
  if (
      "candle_time_max_5_tage" in df.columns
      and "signal_datum" in df.columns
  ):
    valid_time_df = df.dropna(
        subset=["candle_time_max_5_tage", "signal_datum"]
    ).copy()
    if not valid_time_df.empty:
      valid_time_df["max_date"] = pd.to_datetime(
          valid_time_df["candle_time_max_5_tage"], errors="coerce"
      ).dt.date
      valid_time_df["sig_dt"] = pd.to_datetime(
          valid_time_df["signal_datum"], errors="coerce"
      ).dt.date
      valid_time_df["days_diff"] = (
          valid_time_df["max_date"] - valid_time_df["sig_dt"]
      ).dt.days
      days_filtered = valid_time_df["days_diff"].dropna()
      days_filtered = days_filtered[days_filtered >= 0]
      if not days_filtered.empty:
        avg_days_to_max = round(float(days_filtered.mean()), 1)

  # -------------------------------------------------------------------------
  # UI: METRIKEN ANZEIGEN
  # -------------------------------------------------------------------------
  st.markdown("### 📈 Performance & Kennzahlen Übersicht")

  col1, col2, col3, col4 = st.columns(4)
  with col1:
    st.metric(
        "Performance Elite Signale",
        f"{perf_elite}%",
        help="Durchschnittliche Performance der Elite-Signale",
    )
    st.metric(
        "Perf. 5T End (Elite)",
        f"{perf_5d_end_elite}%",
        help="Durchschnittlicher End-Kurs nach 5 Tagen (Elite)",
    )
  with col2:
    st.metric(
        "Performance Kaufsignale",
        f"{perf_kauf}%",
        help="Durchschnittliche Performance der regulären Kaufsignale",
    )
    st.metric(
        "Perf. 5T End (Kauf)",
        f"{perf_5d_end_kauf}%",
        help="Durchschnittlicher End-Kurs nach 5 Tagen (Kauf)",
    )
  with col3:
    st.metric(
        "Gewinntrades (Quote)",
        f"{win_rate}%",
        f"{total_wins} Wins gesamt",
        help="Anteil positiver Trades im Journal",
    )
    st.metric(
        "Perf. 5T Max (Elite)",
        f"{perf_5d_max_elite}%",
        help="Durchschnittliches Maximum nach 5 Tagen (Elite)",
    )
  with col4:
    st.metric(
        "Ø Tage bis Max-Perf",
        f"{avg_days_to_max} Tage",
        help="Durchschnittliche Anzahl Tage vom Signal bis zum 5T-Hoch",
    )
    st.metric(
        "Perf. 5T Max (Kauf)",
        f"{perf_5d_max_kauf}%",
        help="Durchschnittliches Maximum nach 5 Tagen (Kauf)",
    )

  st.divider()

  # -------------------------------------------------------------------------
  # UI: FILTER & KOMPLETTES JOURNAL ALS TABELLE
  # -------------------------------------------------------------------------
  st.markdown("### 🗂️ Komplettes Signals Journal (Tabelle)")

  # Filteroptionen für die Tabelle
  col_f1, col_f2, col_f3 = st.columns(3)
  with col_f1:
    selected_type = st.selectbox(
        "Nach Signal-Typ filtern",
        ["Alle"] + list(df["signal_typ"].dropna().unique()),
    )
  with col_f2:
    only_favorites = st.checkbox("Nur Favoriten anzeigen")
  with col_f3:
    search_ticker = st.text_input("Ticker Suchen", "").strip().upper()

  # DataFrame filtern
  df_display = df.copy()
  if selected_type != "Alle":
    df_display = df_display[df_display["signal_typ"] == selected_type]
  if only_favorites and "is_favorite" in df_display.columns:
    df_display = df_display[df_display["is_favorite"] == True]
  if search_ticker:
    df_display = df_display[
        df_display["ticker"].str.upper().str.contains(search_ticker, na=False)
    ]

  # Relevante Spalten für die übersichtliche Ansicht auswählen (falls vorhanden)
  preferred_columns = [
      "ticker",
      "signal_datum",
      "signal_typ",
      "einstiegspreis_zum_signal",
      "smi",
      "adx",
      "above_ema20",
      "is_favorite",
      "max_performance_5_tage",
      "end_performance_5_tage",
      "performance_30d_end_pct",
      "status",
  ]
  existing_cols = [c for c in preferred_columns if c in df_display.columns]
  # Restliche Spalten anhängen, die nicht in der Liste sind
  other_cols = [c for c in df_display.columns if c not in existing_cols]
  final_col_order = existing_cols + other_cols

  st.dataframe(
      df_display[final_col_order],
      use_container_width=True,
      hide_index=True,
  )

  st.caption(
      f"Gesamtanzahl Datensätze in Ansicht: {len(df_display)} von"
      f" {len(df)} Einträgen."
  )


# Beispiel für den Aufruf im Hauptskript von Leopold:
if __name__ == "__main__":
  st.set_page_config(
      page_title="Leopold Signals Dashboard", layout="wide"
  )
  from db import get_db_client

  db_client = get_db_client()
  render_leopold_signals_dashboard(db_client)