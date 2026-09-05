import sys
from pathlib import Path
import pandas as pd

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
    "⚡ Nino - Signal Agent",
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
            
            # Sicherer Abfang von None/NULL Werten für die Performance
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
# TAB 3: NINO (Signal Performance Dashboard)
# ==========================================
with tab_nino:
    st.subheader("⚡ Nino - Signal Agent")
    st.markdown("Visuelle Auswertung der autonomen 5-Tages-Signal-Analysen.")
    
    st.divider()

    history_data = nino.get_signals_history()
    
    if history_data:
        df_journal = pd.DataFrame(history_data)
        
        # Nur ausgewertete Signale für das Dashboard nutzen
        df_eval = df_journal[df_journal['status'].str.contains('Ausgewertet', na=False)].copy()
        
        if not df_eval.empty:
            # 1. KPI-METRIKEN OBEN
            total_eval = len(df_eval)
            wins = len(df_eval[df_eval['end_performance_5_tage'] > 0])
            losses = len(df_eval[df_eval['end_performance_5_tage'] <= 0])
            win_rate = (wins / total_eval) * 100 if total_eval > 0 else 0
            
            avg_perf_total = df_eval['end_performance_5_tage'].mean()
            max_perf_all = df_eval['max_performance_5_tage'].max() if 'max_performance_5_tage' in df_eval.columns else 0
            
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1: st.metric("Ausgewertete Signale", f"{total_eval}")
            with col2: st.metric("Win-Rate", f"{win_rate:.1f}%", f"{wins} Win / {losses} Loss")
            with col3: st.metric("Ø End-Performance (5D)", f"{avg_perf_total:+.2f}%")
            with col4: st.metric("Bester Peak (5D)", f"{max_perf_all:+.2f}%")
            with col5: st.metric("Offene Signale", f"{len(df_journal) - total_eval}")
                
            st.markdown("---")
            
            # 2. VISUELLE CHARTS (DASHBOARD-BEREICH)
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.markdown("#### 📊 Performance nach Ticker (End-Perf. in %)")
                if 'ticker' in df_eval.columns and 'end_performance_5_tage' in df_eval.columns:
                    df_chart = df_eval.set_index('ticker')[['end_performance_5_tage']].dropna()
                    if not df_chart.empty:
                        st.bar_chart(df_chart)
                    else:
                        st.info("Keine Daten für Chart verfügbar.")
                        
            with col_chart2:
                st.markdown("#### 🚀 Max-Peak vs. End-Performance")
                if 'max_performance_5_tage' in df_eval.columns and 'end_performance_5_tage' in df_eval.columns:
                    df_comparison = df_eval.set_index('ticker')[['max_performance_5_tage', 'end_performance_5_tage']].dropna()
                    if not df_comparison.empty:
                        st.line_chart(df_comparison)
                    else:
                        st.info("Keine Vergleichsdaten verfügbar.")
        else:
            st.warning("⚠️ Noch keine 5-Tages-Auswertungen vorhanden. Sobald Signale ausgewertet sind, füllt sich das Dashboard automatisch.")
    else:
        st.info("Das Journal ist komplett leer.")

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