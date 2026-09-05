import sys
from pathlib import Path
import json
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# Setzt das Hauptverzeichnis fest in den Suchpfad von Python
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

import streamlit as st
from supabase import create_client

# Importiere die Mitarbeiter-Klassen
from employees.otto import OttoAnalyst
from employees.nino import NinoSignalsAssistant
from employees.peter import PeterInsiderAnalyst

st.set_page_config(layout="wide", page_title="VisionDZ - Team & Kommandozentrale", page_icon="🏢")

if not st.session_state.get("password_correct", False):
    st.warning("Bitte melde dich zuerst auf der Hauptseite an.")
    st.stop()

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# Mitarbeiter-Instanzen erzeugen
otto = OttoAnalyst(supabase)
nino = NinoSignalsAssistant(supabase)
peter = PeterInsiderAnalyst(supabase)

st.title("🏢 VisionDZ - Team & Kommandozentrale")

# --- DIE TABS DEFINIEREN ---
tab_teamroom, tab_otto, tab_nino, tab_peter = st.tabs([
    "💬 Teamroom", 
    "📊 Otto (History & Macro)", 
    "⚡ Signals Journal (Nino)",
    "🕵️ Peter (Market Intel)"
])

# ==========================================
# TAB 1: DER TEAMROOM (Zusammenführung & Synthese)
# ==========================================
with tab_teamroom:
    st.subheader("Tägliches Standup & Synthesis")
    st.markdown("Nach Ray Dalios Prinzipien: **Radical Truth & Radical Open-Mindedness**.")
    
    selected_depot = st.selectbox(
        "Fokus-Depot für dieses Meeting:",
        ["Invest (Langfristiges Fundament / Core)", "Swing (Mittelfristige Trendfolge)", "Risiko (Aggressive / Spekulative Plays)"],
        key="teamroom_depot_select"
    )
    
    st.divider()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📊 Ottos aktueller Stand")
        logs = otto.get_logs()
        if logs:
            latest_otto = logs[0]
            st.write(f"**Marktphase:** {latest_otto.get('market_phase', 'N/A')}")
            st.info(latest_otto.get('insight', 'Keine Daten'))
        else:
            st.warning("Otto hat noch kein Standup durchgeführt. Wechsle in den Tab 'Otto'.")
            
    with col2:
        st.markdown("#### ⚡ Ninos letzte Journal-Aktivität")
        journal_logs = nino.get_signals_history()
        if journal_logs:
            latest_nino = journal_logs[0]
            st.write(f"**Letzter Ticker:** {latest_nino.get('ticker')} ({latest_nino.get('signal_typ')})")
            
            perf = latest_nino.get('max_performance_5_tage')
            perf_val = float(perf) if perf is not None else 0.0
            
            st.info(f"Status: {latest_nino.get('status')} | Max-Perf (5D): {perf_val:+.2f}%")
        else:
            st.warning("Das Journal ist noch leer.")
        
    st.divider()
    
    team_conclusion = st.text_area(
        "Finaler Team-Beschluss für das gewählte Depot:",
        placeholder="Z.B.: 'Aufgrund von Ottos Makro-Analyse gewichten wir das Invest-Depot defensiver...'"
    )
    if st.button("💾 Entschluss speichern"):
        if team_conclusion:
            try:
                supabase.table("team_decisions").insert({
                    "depot_focus": selected_depot,
                    "decision_text": team_conclusion
                }).execute()
                st.success("Entschluss erfolgreich verankert!")
            except Exception as e:
                st.error(f"Fehler: {e}")
        else:
            st.warning("Bitte Text eingeben.")

# ==========================================
# TAB 2: OTTO (Nutzt ausschließlich `employees/otto.py`)
# ==========================================
with tab_otto:
    st.subheader(f"📊 {otto.name}")
    st.caption(otto.description)
    
    col_o1, col_o2 = st.columns([2, 1])
    
    with col_o1:
        if st.button("🚀 Otto: Analyse & Tages-Standup starten", key="btn_run_otto"):
            with st.spinner("Otto analysiert..."):
                success, msg = otto.run_analysis()
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(f"Fehler: {msg}")
        
        logs = otto.get_logs()
        if logs:
            st.markdown("### 📚 Ottos Logbuch")
            for log in logs:
                with st.expander(f"Standup vom {log['analysis_date']} – Phase: {log.get('market_phase', 'N/A')}"):
                    st.write(log['insight'])
                    if log.get('user_feedback'):
                        st.info(f"Dein Feedback: {log['user_feedback']}")
        else:
            st.info("Noch keine Berichte im Gedächtnis.")
            
    with col_o2:
        st.markdown("#### 💬 Direkt mit Otto sprechen")
        user_input = st.text_area("Anweisung an Otto:", placeholder="Z.B.: 'Achte stärker auf Rohstoffe.'", key="otto_feedback_input")
        if st.button("Anweisung senden", key="btn_send_otto_fb"):
            if user_input:
                success, msg = otto.save_feedback(user_input)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning(msg)
            else:
                st.warning("Bitte Nachricht eingeben.")

# ==========================================
# TAB 3: NINO (Signals Journal & Auswertung)
# ==========================================
with tab_nino:
    st.subheader("⚡ Signals Journal (Nino)")
    st.markdown("Autonomes Archiv aller Screener-Signale inklusive 5-Tages-Peak- und Schlusskurs-Auswertung.")
    
    st.divider()

    # Hintergrund-Routine von Nino beim Laden des Tabs anstoßen
    try:
        if hasattr(nino, 'background_routine'):
            nino.background_routine()
    except Exception:
        pass

    history_data = nino.get_signals_history()
    
    if history_data:
        df_journal = pd.DataFrame(history_data)
        
        # Auswertungs-Metriken (oben im Tab)
        df_eval = df_journal[df_journal['status'].str.contains('Ausgewertet', na=False)].copy()
        
        if not df_eval.empty:
            total_eval = len(df_eval)
            wins = len(df_eval[df_eval['end_performance_5_tage'] > 0])
            losses = len(df_eval[df_eval['end_performance_5_tage'] <= 0])
            
            avg_perf_total = df_eval['end_performance_5_tage'].mean()
            
            df_ema = df_eval[df_eval['above_ema20'] == True]
            avg_perf_ema = df_ema['end_performance_5_tage'].mean() if not df_ema.empty else 0.0
            
            df_fav = df_eval[df_eval['is_favorite'] == True]
            avg_perf_fav = df_fav['end_performance_5_tage'].mean() if not df_fav.empty else 0.0
            
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1: st.metric("Ausgewertet", f"{total_eval}")
            with col2: st.metric("Gewinn / Verlust", f"{wins} 🟢 / {losses} 🔴")
            with col3: st.metric("Ø Performance", f"{avg_perf_total:.2f}%")
            with col4: st.metric("Ø Perf. (Über EMA20)", f"{avg_perf_ema:.2f}%")
            with col5: st.metric("Ø Perf. (Favoriten)", f"{avg_perf_fav:.2f}%")
                
            st.markdown("---")
        else:
            st.info("ℹ️ Noch keine 5-Tages-Auswertungen vorhanden. Nino wertet automatisch im Hintergrund aus, sobald Signale 5 Tage alt sind.")

        st.subheader("📁 Vollständiges Signal-Journal")
        
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

        display_cols = [
            'ticker', 'signal_datum', 'signal_typ', 'einstiegspreis_zum_signal', 
            'smi', 'adx', 'is_favorite', 'above_ema20', 
            'max_performance_5_tage', 'end_performance_5_tage', 'status'
        ]
        existing_cols = [c for c in display_cols if c in df_journal.columns]

        df_display = df_journal[existing_cols].copy()
        if "id" in df_display.columns:
            df_display = df_display.drop(columns=["id"])

        st.dataframe(df_display, column_config=conf, hide_index=True, use_container_width=True)

    else:
        st.info("Das Signals Journal ist noch leer. Sobald Nino im Hintergrund seine Arbeit verrichtet, erscheinen hier die Daten.")

# ==========================================
# TAB 4: PETER (Market Intel & Insider)
# ==========================================
with tab_peter:
    st.subheader(f"🕵️ {peter.name}")
    st.caption(peter.description)
    
    if st.button("🔄 Peter: Markt-Intel & Kennzahlen aktualisieren", key="btn_run_peter"):
        with st.spinner("Peter holt aktuelle Marktdaten und bereinigt alte Einträge (>6 Monate)..."):
            success, msg = peter.fetch_market_intel()
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
                
    st.divider()
    
    latest_intel = peter.get_latest_intel()
    if latest_intel:
        st.markdown(f"### 📌 Bericht vom {latest_intel.get('analysis_date')}")
        
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**Insider & Aktivität:**\n\n{latest_intel.get('insider_activity')}")
            st.warning(f"**Analysten-Konsens / Bewertung:**\n\n{latest_intel.get('analyst_consensus')}")
        with col2:
            st.success(f"**Markt- & News-Summary:**\n\n{latest_intel.get('market_news_summary')}")
    else:
        st.info("Noch keine Markt-Intel vorhanden. Starte die Aktualisierung über den Button.")