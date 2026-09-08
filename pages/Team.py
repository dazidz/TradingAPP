from datetime import datetime, timedelta
from pathlib import Path
import sys
import google.generativeai as genai
import pandas as pd
import streamlit as st
from supabase import create_client
import yfinance as yf

# Setzt das Hauptverzeichnis fest in den Suchpfad von Python
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
  sys.path.append(str(root_dir))

st.set_page_config(
    layout="wide",
    page_title="VisionDZ - Team & Kommandozentrale",
    page_icon="🏢",
)

if not st.session_state.get("password_correct", False):
  st.warning("Bitte melde dich zuerst auf der Hauptseite an.")
  st.stop()

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

st.title("🏢 VisionDZ - Team & Kommandozentrale")

# --- DIE TABS DEFINIEREN (Inklusive Joris & Jano) ---
tab_teamroom, tab_jano, tab_peter, tab_otto, tab_nino, tab_aris = st.tabs([
    "💬 Teamroom & Joris",
    "🌍 Jano (Macro)",
    "🕵️ Peter (Micro/Insider)",
    "📊 Otto (History)",
    "⚡ Nino (Signals)",
    "🤖 Aris (Performance)",
])

# ==========================================
# TAB 1: DER TEAMROOM & JORIS (PORTFOLIO MANAGER)
# ==========================================
with tab_teamroom:
  try:
    from employees.joris import JorisPortfolioManager

    joris = JorisPortfolioManager(supabase)

    st.subheader("Tägliches Standup & Portfolio-Synthese")
    st.markdown(
        "Nach Ray Dalios Prinzipien: **Radical Truth & Radical Open-Mindedness**."
    )

    # Depot-Auswahl für Joris & Team-Beschluss
    selected_depot_label = st.selectbox(
        "Fokus-Depot für dieses Meeting:",
        [
            "Invest (Langfristiges Fundament / Core)",
            "Swing (Mittelfristige Trendfolge)",
            "High Risk (Aggressive / Spekulative Plays)",
        ],
        key="teamroom_depot_select",
    )

    # Mapping für den internen Code (invest, swing, high_risk)
    depot_mapping = {
        "Invest (Langfristiges Fundament / Core)": "invest",
        "Swing (Mittelfristige Trendfolge)": "swing",
        "High Risk (Aggressive / Spekulative Plays)": "high_risk",
    }
    current_depot_focus = depot_mapping[selected_depot_label]

    col_j1, col_j2 = st.columns([2, 1])
    with col_j1:
      if st.button(
          "🚀 Joris: Portfolio-Synthese für dieses Mandat starten",
          type="primary",
      ):
        with st.spinner(
            f"Joris synthetisiert Berichte für '{current_depot_focus}'..."
        ):
          success, msg = joris.run_synthesis(depot_focus=current_depot_focus)
          if success:
            st.success(msg)
            st.rerun()
          else:
            st.error(msg)

    st.divider()

    # Joris neuesten Bericht für dieses Depot anzeigen
    latest_joris = joris.get_latest_report(depot_focus=current_depot_focus)
    if latest_joris:
      st.markdown(f"### 🎯 Joris Mandats-Empfehlung ({selected_depot_label})")
      st.info(latest_joris["report_content"])
    else:
      st.warning(
          "Joris hat für dieses Depot noch keine Synthese durchgeführt."
      )

    st.divider()
    st.markdown("### 📊 Letzte Einzelberichte im Team")

    col1, col2, col3, col4 = st.columns(4)

    def get_last_agent_report(agent_name):
      try:
        res = (
            supabase.table("agent_reports")
            .select("*")
            .eq("agent_name", agent_name)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0]["report_content"] if res.data else "Kein Bericht."
      except Exception:
        return "Fehler beim Laden."

    with col1:
      st.markdown("#### 🌍 Jano (Macro)")
      st.write(get_last_agent_report("Jano")[:300] + "...")

    with col2:
      st.markdown("#### 🕵️ Peter (Micro)")
      st.write(get_last_agent_report("Peter")[:300] + "...")

    with col3:
      st.markdown("#### 📊 Otto (History)")
      st.write(get_last_agent_report("Otto")[:300] + "...")

    with col4:
      st.markdown("#### 🤖 Aris (Performance)")
      st.write(get_last_agent_report("Aris")[:300] + "...")

  except Exception as e:
    st.error(f"Fehler im Teamroom: {e}")

# ==========================================
# TAB 2: JANO (MACRO ANALYST)
# ==========================================
with tab_jano:
  try:
    from employees.jano import JanoMacroAnalyst

    jano = JanoMacroAnalyst(supabase)
    st.subheader(f"🌍 {jano.name}")
    st.caption(jano.description)

    if st.button("🚀 Jano: Makro-Analyse starten", key="btn_run_jano"):
      with st.spinner("Jano analysiert die Makrolage..."):
        success, msg = jano.run_analysis()
        if success:
          st.success(msg)
          st.rerun()
        else:
          st.error(msg)

    st.divider()
    latest_jano = jano.get_latest_report()
    if latest_jano:
      st.markdown(f"### Bericht vom {latest_jano['created_at'][:16]}")
      st.write(latest_jano["report_content"])
    else:
      st.info("Noch kein Makro-Bericht vorhanden.")
  except Exception as e:
    st.error(f"Jano-Tab aktuell nicht verfügbar (Fehler: {e})")

# ==========================================
# TAB 3: PETER (MARKET INTEL & INSIDER)
# ==========================================
with tab_peter:
  try:
    from employees.peter import PeterInsiderAnalyst

    peter = PeterInsiderAnalyst(supabase)

    st.subheader(f"🕵️ {peter.name}")
    st.caption(peter.description)

    if st.button("🔄 Peter: Fundamentaldaten & Insider analysieren"):
      with st.spinner("Peter holt Watchlist & Insider-Daten..."):
        success, msg = peter.run_analysis()
        if success:
          st.success(msg)
          st.rerun()
        else:
          st.error(msg)

    st.divider()
    latest_peter = peter.get_latest_report()
    if latest_peter:
      st.markdown(f"### Bericht vom {latest_peter['created_at'][:16]}")
      st.write(latest_peter["report_content"])
    else:
      st.info("Noch keine Peter-Berichte vorhanden.")
  except Exception as e:
    st.error(f"Peter-Tab aktuell nicht verfügbar (Fehler: {e})")

# ==========================================
# TAB 4: OTTO (HISTORY & PATTERNS)
# ==========================================
with tab_otto:
  try:
    from employees.otto import OttoAnalyst

    otto = OttoAnalyst(supabase)

    st.subheader(f"📊 {otto.name}")
    st.caption(otto.description)

    if st.button("🚀 Otto: Historisches Muster-Matching starten"):
      with st.spinner("Otto gleicht mit der Börsenhistorie ab..."):
        success, msg = otto.run_analysis()
        if success:
          st.success(msg)
          st.rerun()
        else:
          st.error(msg)

    st.divider()
    latest_otto = otto.get_latest_report()
    if latest_otto:
      st.markdown(f"### Bericht vom {latest_otto['created_at'][:16]}")
      st.write(latest_otto["report_content"])
    else:
      st.info("Noch keine Otto-Berichte vorhanden.")
  except Exception as e:
    st.error(f"Otto-Tab aktuell nicht verfügbar (Fehler: {e})")

# ==========================================
# TAB 5: NINO (SIGNAL AGENT)
# ==========================================
with tab_nino:
  try:
    from employees.nino import NinoSignalsAssistant

    nino = NinoSignalsAssistant(supabase)

    st.subheader("⚡ Nino - Signal Agent")
    st.markdown("Visuelle Auswertung der autonomen 5-Tages-Signal-Analysen.")
    st.divider()

    history_data = nino.get_signals_history()
    if history_data:
      df_journal = pd.DataFrame(history_data)
      df_eval = (
          df_journal[df_journal["status"].str.contains("Ausgewertet", na=False)]
          .copy()
      )

      if not df_eval.empty:
        total_eval = len(df_eval)
        wins = len(df_eval[df_eval["end_performance_5_tage"] > 0])
        losses = len(df_eval[df_eval["end_performance_5_tage"] <= 0])
        win_rate = (wins / total_eval) * 100 if total_eval > 0 else 0

        avg_perf_total = df_eval["end_performance_5_tage"].mean()
        max_perf_all = (
            df_eval["max_performance_5_tage"].max()
            if "max_performance_5_tage" in df_eval.columns
            else 0
        )
        fav_count = (
            len(df_journal[df_journal["is_favorite"] == True])
            if "is_favorite" in df_journal.columns
            else 0
        )

        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
          st.metric("Ausgewertet", f"{total_eval}")
        with col2:
          st.metric("Win-Rate", f"{win_rate:.1f}%", f"{wins}W/{losses}L")
        with col3:
          st.metric("Ø End-Perf.", f"{avg_perf_total:+.2f}%")
        with col4:
          st.metric("Bester Peak", f"{max_perf_all:+.2f}%")
        with col5:
          st.metric("Favoriten", f"{fav_count}")
        with col6:
          st.metric("Offen", f"{len(df_journal) - total_eval}")
      else:
        st.warning("⚠️ Noch keine 5-Tages-Auswertungen vorhanden.")
    else:
      st.info("Das Journal ist komplett leer.")
  except Exception as e:
    st.error(f"Nino-Tab aktuell nicht verfügbar (Fehler: {e})")

# ==========================================
# TAB 6: ARIS (PERFORMANCE MANAGER & CHAT)
# ==========================================
with tab_aris:
  st.subheader("🤖 Aris - Performance Manager")
  st.markdown(
      "Dein KI-Agent analysiert das Signals-Journal, das Trading-Journal, "
      "den Screener-Quellcode und steht dir im Chat für Rückfragen zur Verfügung."
  )

  if "messages_aris" not in st.session_state:
    st.session_state.messages_aris = []

  aris_dna = """
    Du bist Aris, der leitende Performance Manager in dieser Trading-Anwendung. Deine Aufgabe ist es, die Performance objektiv, datenbasiert und gnadenlos ehrlich zu analysieren. Du verzichtest auf leere Floskeln und Schönfärberei. 
    Analysiere die übergebenen Datenpunkte:
    1. Signals Journal (inkl. 5-Tage und 1-Monats-Meilensteine)
    2. Trading Journal (geschlossene Trades inkl. Post-Exit-Tracking)
    3. Screener-Quellcode (auf Filterfehler, Schwachstellen und verpasste Chancen prüfen)
    4. Watchlist (nach Asset-Kategorien: Invest, Swing, High Risk)

    Finde Muster, vergleiche Gewinner vs. Verlierer, bewerte ob Trades zu früh geschlossen wurden und liefere konkrete, direkt umsetzbare Handlungsempfehlungen.
    """

  # Letzten Aris-Report laden, falls Chat leer
  if not st.session_state.messages_aris:
    try:
      saved_report_res = (
          supabase.table("agent_reports")
          .select("*")
          .eq("agent_name", "Aris")
          .order("created_at", desc=True)
          .limit(1)
          .execute()
      )
      if saved_report_res.data:
        latest_report = saved_report_res.data[0]
        st.session_state.messages_aris.append({
            "role": "assistant",
            "content": (
                "**Letzter gespeicherter Report ("
                f"{latest_report['created_at'][:16]}):**\n\n"
                + latest_report["report_content"]
            ),
        })
    except Exception:
      pass

  if st.button("🚀 Aris Analyse & Screener-Review starten", type="primary"):
    with st.spinner("Aris analysiert Datenbanken und Code..."):
      try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)

        signals_res = supabase.table("signals_journal").select("*").execute()
        journal_res = supabase.table("trade_journal").select("*").execute()
        signals_df = pd.DataFrame(signals_res.data)
        journal_df = pd.DataFrame(journal_res.data)

        context_data = f"""
            --- SIGNALS JOURNAL ---
            {signals_df.to_string() if not signals_df.empty else "Keine Signale"}
            --- TRADING JOURNAL ---
            {journal_df.to_string() if not journal_df.empty else "Keine Trades"}
            """

        model = genai.GenerativeModel(
            model_name="gemini-3.6-flash", system_instruction=aris_dna
        )
        response = model.generate_content(
            "Erstelle deinen Analyse-Report:\n\n" + context_data
        )
        report_content = response.text

        supabase.table("agent_reports").insert({
            "agent_name": "Aris",
            "report_content": report_content,
        }).execute()

        st.session_state.messages_aris.append(
            {"role": "assistant", "content": report_content}
        )
        st.success("Analyse erfolgreich abgeschlossen!")
        st.rerun()
      except Exception as e:
        st.error(f"⚠️ Fehler: {e}")

  st.markdown("---")
  st.markdown("### 💬 Diskussion mit Aris")

  for message in st.session_state.messages_aris:
    with st.chat_message(message["role"]):
      st.markdown(message["content"])

  if user_query := st.chat_input("Stelle Aris eine Frage..."):
    st.session_state.messages_aris.append(
        {"role": "user", "content": user_query}
    )
    with st.chat_message("user"):
      st.markdown(user_query)

    with st.chat_message("assistant"):
      with st.spinner("Aris denkt nach..."):
        try:
          api_key = st.secrets["GEMINI_API_KEY"]
          genai.configure(api_key=api_key)

          gemini_history = []
          for m in st.session_state.messages_aris[:-1]:
            role = "user" if m["role"] == "user" else "model"
            if not gemini_history and role == "model":
              continue
            gemini_history.append({"role": role, "parts": [m["content"]]})

          model = genai.GenerativeModel(
              model_name="gemini-3.6-flash", system_instruction=aris_dna
          )
          chat_session = model.start_chat(history=gemini_history)
          chat_response = chat_session.send_message(user_query)

          answer = chat_response.text
          st.markdown(answer)
          st.session_state.messages_aris.append(
              {"role": "assistant", "content": answer}
          )
        except Exception as chat_err:
          st.error(f"Fehler im Chat: {chat_err}")