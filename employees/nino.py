import os
import sys
import streamlit as st
import pandas as pd

# Hauptverzeichnis in den Pfad aufnehmen, um Module wie `db.py` oder Ninos Klasse zu finden
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from db import get_db_client
# Falls Ninos Klasse in einer eigenen Datei (z.B. nino_assistant.py) liegt, hier importieren.
# Falls der Code direkt hier liegt, kannst du die Klasse natürlich auch direkt hier definieren.
try:
    from nino_assistant import NinoSignalsAssistant
except ImportError:
    # Fallback, falls die Klasse im selben Skript oder anders benannt ist
    pass

# Passwort-Schutz
if "password_correct" not in st.session_state or not st.session_state.password_correct:
    st.error("Bitte zuerst auf der Startseite anmelden!")
    st.stop()

st.title("🤖 Nino (Signals Assistent) - Journal & Auswertung")

# Verbindung zu Supabase & Initialisierung
supabase_client = get_db_client()

# Falls NinoSignalsAssistant hier instanziiert wird:
try:
    nino = NinoSignalsAssistant(supabase_client)
except NameError:
    st.error("Die Klasse NinoSignalsAssistant konnte nicht geladen werden. Bitte Import prüfen.")
    st.stop()

# --- SEITENBAR ---
with st.sidebar:
    st.markdown("### ⚙️ Steuerung")
    if st.button("🔄 Manellen Nino-Lauf starten", use_container_width=True):
        with st.spinner("Nino arbeitet..."):
            logs = nino.daily_routine()
            st.success("Nino-Lauf beendet!")
            for log in logs:
                st.write(f"- {log}")
        st.rerun()
    
    if st.button("🔄 Cache leeren", use_container_width=True):
        st.cache_data.clear()
        st.success("Cache erfolgreich geleert!")
        st.rerun()

# --- NINO KPI-BEREICH ---
st.subheader("📊 Performance-Auswertung (5-Tages-Basis)")

# Daten aus dem Journal laden
history_data = nino.get_signals_history()

if history_data:
    df_journal = pd.DataFrame(history_data)
    
    # Nur ausgewertete Signale für die Metriken betrachten
    df_eval = df_journal[df_journal['status'] == 'Ausgewertet (5D)'].copy()
    
    if not df_eval.empty:
        # Metriken berechnen
        total_eval = len(df_eval)
        wins = len(df_eval[df_eval['end_performance_5_tage'] > 0])
        losses = len(df_eval[df_eval['end_performance_5_tage'] <= 0])
        
        avg_perf_total = df_eval['end_performance_5_tage'].mean()
        
        # EMA20 Filter (True zur Kerzenzeit)
        df_ema = df_eval[df_eval['above_ema20'] == True]
        avg_perf_ema = df_ema['end_performance_5_tage'].mean() if not df_ema.empty else 0.0
        
        # Favoriten Filter (True)
        df_fav = df_eval[df_eval['is_favorite'] == True]
        avg_perf_fav = df_fav['end_performance_5_tage'].mean() if not df_fav.empty else 0.0
        
        # --- UI ANZEIGE (Spalten) ---
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Ausgewertet", f"{total_eval}")
        with col2:
            st.metric("Gewinn / Verlust", f"{wins} 🟢 / {losses} 🔴")
        with col3:
            st.metric("Ø Performance", f"{avg_perf_total:.2f}%")
        with col4:
            st.metric("Ø Perf. (Über EMA20)", f"{avg_perf_ema:.2f}%")
        with col5:
            st.metric("Ø Perf. (Favoriten)", f"{avg_perf_fav:.2f}%")
            
        st.markdown("---")
    else:
        st.info("ℹ️ Es sind noch keine 5-Tages-Auswertungen vorhanden (Nino wartet, bis Signale 5 Tage alt sind).")

    # --- JOURNAL TABELLE ---
    st.subheader("📁 Vollständiges Signal-Journal")
    
    # Konfiguration für die Tabelle
    conf = {
        "ticker": st.column_config.TextColumn("Ticker", width="small"),
        "signal_datum": st.column_config.TextColumn("Signal Datum"),
        "signal_typ": st.column_config.TextColumn("Typ"),
        "einstiegspreis_zum_signal": st.column_config.NumberColumn("Einstieg", format="€%.2f"),
        "smi": st.column_config.NumberColumn("SMI", format="%.2f"),
        "adx": st.column_config.NumberColumn("ADX", format="%.2f"),
        "is_favorite": st.column_config.CheckboxColumn("Favorit"),
        "above_ema20": st.column_config.CheckboxColumn("Über EMA20"),
        "max_performance_5_tage": st.column_config.NumberColumn("Max Perf. (5D)", format="%.2f%%"),
        "end_performance_5_tage": st.column_config.NumberColumn("End Perf. (5D)", format="%.2f%%"),
        "status": st.column_config.TextColumn("Status")
    }

    # Relevante Spalten anzeigen, falls vorhanden
    display_cols = [
        'ticker', 'signal_datum', 'signal_typ', 'einstiegspreis_zum_signal', 
        'smi', 'adx', 'is_favorite', 'above_ema20', 
        'max_performance_5_tage', 'end_performance_5_tage', 'status'
    ]
    existing_cols = [c for c in display_cols if c in df_journal.columns]

    st.dataframe(df_journal[existing_cols], column_config=conf, hide_index=True, use_container_width=True)

else:
    st.info("Keine Journal-Daten in der Supabase-Datenbank gefunden.")