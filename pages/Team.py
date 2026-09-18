from datetime import datetime, timedelta
import os
from pathlib import Path
import sys
from groq import Groq
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

# Sicheres Laden der API-Keys (mit import os)
GROQ_API_KEY = None
GEMINI_API_KEY = None

try:
  GROQ_API_KEY = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
except Exception:
  pass

try:
  GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
except Exception:
  pass

st.title("🏢 VisionDZ - Team & Kommandozentrale")

# --- DIE TABS DEFINIEREN ---
tab_teamroom, tab_jano, tab_peter, tab_otto, tab_nino, tab_aris, tab_leopold = st.tabs([
    "💬 Teamroom & Joris",
    "🌍 Jano (Macro)",
    "🕵️ Peter (Micro/Insider)",
    "📊 Otto (History)",
    "⚡ Nino (Signals)",
    "🤖 Aris (Performance)",
    "⚙️ Leopold (Arbeitsspeicher)",
])

# ==========================================
# TAB 1: DER TEAMROOM & JORIS (GEMINI)
# ==========================================
with tab_teamroom:
  try:
    from employees.joris import JorisPortfolioManager

    joris = JorisPortfolioManager(supabase)

    st.subheader("Tägliches Standup & Portfolio-Synthese")
    st.markdown(
        "Nach Ray Dalios Prinzipien: **Radical Truth & Radical"
        " Open-Mindedness**."
    )

    selected_depot_label = st.selectbox(
        "Fokus-Depot für dieses Meeting:",
        [
            "Invest (Langfristiges Fundament / Core)",
            "Swing (Mittelfristige Trendfolge)",
            "High Risk (Aggressive / Spekulative Plays)",
        ],
        key="teamroom_depot_select",
    )

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
          success, msg = joris.run_synthesis(
              depot_focus=current_depot_focus, api_key=GEMINI_API_KEY
          )
          if success:
            st.success(msg)
            st.rerun()
          else:
            st.error(msg)

    st.divider()

    latest_joris = joris.get_latest_report(depot_focus=current_depot_focus)
    if latest_joris:
      st.markdown(f"### 🎯 Joris Mandats-Empfehlung ({selected_depot_label})")
      st.info(latest_joris["report_content"])
    else:
      st.warning(
          "Joris hat für dieses Depot noch keine Synthese durchgeführt."
      )

    # INTERAKTIVER CHAT MIT JORIS
    st.divider()
    st.markdown(f"### 🤖 Diskussion mit Joris ({selected_depot_label})")

    chat_session_key = f"joris_chat_history_{current_depot_focus}"
    if chat_session_key not in st.session_state:
      st.session_state[chat_session_key] = []

    for message in st.session_state[chat_session_key]:
      with st.chat_message(message["role"]):
        st.markdown(message["content"])

    if user_query_joris := st.chat_input(
        f"Diskutiere mit Joris über das Mandat '{selected_depot_label}'..."
    ):
      st.session_state[chat_session_key].append(
          {"role": "user", "content": user_query_joris}
      )
      with st.chat_message("user"):
        st.markdown(user_query_joris)

      with st.chat_message("assistant"):
        with st.spinner("Joris prüft die Daten und antwortet..."):
          success_chat, reply_chat = joris.chat_with_joris(
              depot_focus=current_depot_focus,
              user_message=user_query_joris,
              chat_history=st.session_state[chat_session_key][:-1],
              api_key=GEMINI_API_KEY,
          )
          if success_chat:
            st.markdown(reply_chat)
            st.session_state[chat_session_key].append(
                {"role": "assistant", "content": reply_chat}
            )
          else:
            st.error(reply_chat)

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
# TAB 2: JANO (MACRO ANALYST - GEMINI)
# ==========================================
with tab_jano:
  try:
    from employees.jano import JanoMacroAnalyst

    jano = JanoMacroAnalyst(supabase)
    st.subheader(f"🌍 {jano.name}")
    st.caption(jano.description)

    if st.button("🚀 Jano: Makro-Analyse starten", key="btn_run_jano"):
      with st.spinner("Jano analysiert die Makrolage..."):
        success, msg = jano.run_analysis(api_key=GEMINI_API_KEY)
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
# TAB 3: PETER (MARKET INTEL & INSIDER - GROQ)
# ==========================================
with tab_peter:
  try:
    from employees.peter import PeterInsiderAnalyst

    peter = PeterInsiderAnalyst(supabase)

    st.subheader(f"🕵️ {peter.name}")
    st.caption(peter.description)

    if st.button("🔄 Peter: Fundamentaldaten & Insider analysieren"):
      with st.spinner("Peter holt Watchlist & Insider-Daten..."):
        success, msg = peter.run_analysis(api_key=GROQ_API_KEY)
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
# TAB 4: OTTO (HISTORY & PATTERNS - GEMINI)
# ==========================================
with tab_otto:
  try:
    from employees.otto import OttoAnalyst

    otto = OttoAnalyst(supabase)

    st.subheader(f"📊 {otto.name}")
    st.caption(otto.description)

    if st.button("🚀 Otto: Historisches Muster-Matching starten"):
      with st.spinner("Otto gleicht mit der Börsenhistorie ab..."):
        success, msg = otto.run_analysis(api_key=GEMINI_API_KEY)
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
# TAB 5: NINO (SIGNALS & ARIS ARBEITSSPEICHER)
# ==========================================
with tab_nino:
  try:
    st.subheader("⚡ Nino - Signal Agent & Arbeitsspeicher")
    st.markdown("Zentrale Visualisierung des `aris_arbeitsspeicher` (befüllt durch Nino).")
    st.divider()

    # Daten direkt aus der aris_arbeitsspeicher Tabelle laden (nach candle_time sortiert)
    try:
        res = supabase.table("aris_arbeitsspeicher").select("*").order("candle_time", desc=True).execute()
        data = res.data if res and res.data else []
    except Exception as e:
        st.error(f"Fehler beim Laden des Arbeitsspeichers: {e}")
        data = []

    if not data:
        st.info("Keine Daten im `aris_arbeitsspeicher` gefunden. Nino verarbeitet die Daten im Hintergrund oder per GitHub Action.")
    else:
        df = pd.DataFrame(data)

        # --- Filter-Bereich ---
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            sources = ["Alle"] + list(df["source"].dropna().unique()) if "source" in df.columns else ["Alle"]
            selected_source = st.selectbox("Nach Quelle filtern", sources, key="nino_source_filter")
        with col_f2:
            only_favorites = st.checkbox("Nur Favoriten anzeigen", value=False, key="nino_fav_filter")

        # Filter anwenden
        filtered_df = df.copy()
        if selected_source != "Alle":
            filtered_df = filtered_df[filtered_df["source"] == selected_source]
        if only_favorites and "is_favorite" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["is_favorite"] == True]

        # --- KPIs / Kennzahlen oben ---
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Gesamt Einträge", len(filtered_df))
        with col2:
            avg_end_perf = filtered_df["end_performance_5_tage"].mean() if "end_performance_5_tage" in filtered_df.columns else 0
            st.metric("Ø 5D End-Performance", f"{avg_end_perf:+.2f}%" if pd.notnull(avg_end_perf) else "0.0%")
        with col3:
            avg_max_perf = filtered_df["max_performance_5_tage"].mean() if "max_performance_5_tage" in filtered_df.columns else 0
            st.metric("Ø 5D Max-Performance", f"{avg_max_perf:+.2f}%" if pd.notnull(avg_max_perf) else "0.0%")
        with col4:
            fav_count = filtered_df["is_favorite"].sum() if "is_favorite" in filtered_df.columns else 0
            st.metric("Favoriten in Ansicht", int(fav_count))

        st.divider()

        # --- Datentabelle anzeigen ---
        st.subheader("📊 Arbeitsspeicher-Daten")
        display_columns = [
            "ticker", "source", "candle_time", "signal_typ", 
            "einstiegspreis_zum_signal", "max_kurs_5_tage", "max_performance_5_tage", 
            "end_kurs_5_tage", "end_performance_5_tage", "is_favorite", "status"
        ]
        existing_cols = [col for col in display_columns if col in filtered_df.columns]
        
        st.dataframe(
            filtered_df[existing_cols],
            use_container_width=True,
            hide_index=True
        )

        # CSV Export Button
        csv = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Gefilterte Daten als CSV herunterladen",
            data=csv,
            file_name="aris_arbeitsspeicher_export.csv",
            mime="text/csv",
        )

  except Exception as e:
    st.error(f"Nino-Tab aktuell nicht verfügbar (Fehler: {e})")

# ==========================================
# TAB 6: ARIS (PERFORMANCE MANAGER & CHAT - GROQ)
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

    Finde Muster, vergleiche Gewinner vs. Verlierer, bewerte ob Trades zu früh geschlossen wurden und liefer konkrete, direkt umsetzbare Handlungsempfehlungen.
    """

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
        groq_client = Groq(api_key=GROQ_API_KEY)

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

        completion = groq_client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": aris_dna},
                {
                    "role": "user",
                    "content": (
                        "Erstelle deinen Analyse-Report:\n\n" + context_data
                    ),
                },
            ],
            temperature=0.1,
        )
        report_content = completion.choices[0].message.content

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

  if user_query := st.chat_input("Stelle Aris eine Frage...", key="aris_chat_input"):
    st.session_state.messages_aris.append(
        {"role": "user", "content": user_query}
    )
    with st.chat_message("user"):
      st.markdown(user_query)

    with st.chat_message("assistant"):
      with st.spinner("Aris denkt nach..."):
        try:
          groq_client = Groq(api_key=GROQ_API_KEY)

          groq_history = [{"role": "system", "content": aris_dna}]
          for m in st.session_state.messages_aris[:-1]:
            role = "user" if m["role"] == "user" else "assistant"
            groq_history.append({"role": role, "content": m["content"]})

          completion = groq_client.chat.completions.create(
              model="openai/gpt-oss-120b",
              messages=groq_history,
              temperature=0.1,
          )

          answer = completion.choices[0].message.content
          st.markdown(answer)
          st.session_state.messages_aris.append(
              {"role": "assistant", "content": answer}
          )
        except Exception as chat_err:
          st.error(f"Fehler im Chat: {chat_err}")

# ==========================================
# TAB 7: LEOPOLD (SYSTEM SUPPORT)
# ==========================================
with tab_leopold:
  try:
    st.subheader("⚙️ Leopold - System Support & Überwachung")
    st.markdown(
        "Leopold überwacht den Systemstatus und sekundäre Hintergrundprozesse. "
        "Die zentrale Datenverwaltung wurde vollständig an Nino übertragen."
    )
    st.divider()

    st.info("Alle Systeme laufen stabil. Keine manuellen Eingriffe über diesen Tab erforderlich.")

  except Exception as e:
    st.error(f"Leopold-Tab aktuell nicht verfügbar (Fehler: {e})")