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

# --- DIE TABS DEFINIEREN ---
tab_teamroom, tab_otto, tab_nino, tab_peter, tab_aris = st.tabs([
    "💬 Teamroom",
    "📊 Otto (History & Macro)",
    "⚡ Nino - Signal Agent",
    "🕵️ Peter (Market Intel)",
    "🤖 Aris (Performance Manager)",
])

# ==========================================
# TAB 1: DER TEAMROOM
# ==========================================
with tab_teamroom:
  try:
    st.subheader("Tägliches Standup & Synthesis")
    st.markdown(
        "Nach Ray Dalios Prinzipien: **Radical Truth & Radical Open-Mindedness**."
    )

    selected_depot = st.selectbox(
        "Fokus-Depot für dieses Meeting:",
        [
            "Invest (Langfristiges Fundament / Core)",
            "Swing (Mittelfristige Trendfolge)",
            "Risiko (Aggressive / Spekulative Plays)",
        ],
        key="teamroom_depot_select",
    )

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
      st.markdown("#### 📊 Ottos aktueller Stand")
      try:
        from employees.otto import OttoAnalyst

        otto = OttoAnalyst(supabase)
        logs = otto.get_logs()
        if logs:
          latest_otto = logs[0]
          st.write(f"**Marktphase:** {latest_otto.get('market_phase', 'N/A')}")
          st.info(latest_otto.get("insight", "Keine Daten"))
        else:
          st.warning("Otto hat noch kein Standup durchgeführt.")
      except Exception as e:
        st.error(f"Otto konnte nicht geladen werden: {e}")

    with col2:
      st.markdown("#### ⚡ Ninos letzte Journal-Aktivität")
      try:
        from employees.nino import NinoSignalsAssistant

        nino = NinoSignalsAssistant(supabase)
        journal_logs = nino.get_signals_history()
        if journal_logs:
          latest_nino = journal_logs[0]
          st.write(
              f"**Letzter Ticker:** {latest_nino.get('ticker')}"
              f" ({latest_nino.get('signal_typ')})"
          )
          perf = latest_nino.get("max_performance_5_tage")
          perf_val = float(perf) if perf is not None else 0.0
          st.info(
              f"Status: {latest_nino.get('status')} | Max-Perf (5D):"
              f" {perf_val:+.2f}%"
          )
        else:
          st.warning("Das Journal ist noch leer.")
      except Exception as e:
        st.error(f"Nino konnte nicht geladen werden: {e}")

    st.divider()
    team_conclusion = st.text_area(
        "Finaler Team-Beschluss für das gewählte Depot:",
        placeholder=(
            "Z.B.: 'Aufgrund von Ottos Makro-Analyse gewichten wir das"
            " Invest-Depot defensiver...'"
        ),
    )
    if st.button("💾 Entschluss speichern"):
      if team_conclusion:
        try:
          supabase.table("team_decisions").insert({
              "depot_focus": selected_depot,
              "decision_text": team_conclusion,
          }).execute()
          st.success("Entschluss erfolgreich verankert!")
        except Exception as e:
          st.error(f"Fehler beim Speichern: {e}")
      else:
        st.warning("Bitte Text eingeben.")
  except Exception as e:
    st.error(f"Fehler im Teamroom: {e}")

# ==========================================
# TAB 2: OTTO
# ==========================================
with tab_otto:
  try:
    from employees.otto import OttoAnalyst

    otto = OttoAnalyst(supabase)

    st.subheader(f"📊 {otto.name}")
    st.caption(otto.description)

    col_o1, col_o2 = st.columns([2, 1])
    with col_o1:
      if st.button(
          "🚀 Otto: Analyse & Tages-Standup starten", key="btn_run_otto"
      ):
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
          with st.expander(
              f"Standup vom {log['analysis_date']} – Phase:"
              f" {log.get('market_phase', 'N/A')}"
          ):
            st.write(log["insight"])
            if log.get("user_feedback"):
              st.info(f"Dein Feedback: {log['user_feedback']}")
      else:
        st.info("Noch keine Berichte im Gedächtnis.")

    with col_o2:
      st.markdown("#### 💬 Direkt mit Otto sprechen")
      user_input = st.text_area(
          "Anweisung an Otto:",
          placeholder="Z.B.: 'Achte stärker auf Rohstoffe.'",
          key="otto_feedback_input",
      )
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
  except Exception as e:
    st.error(f"Otto-Tab aktuell nicht verfügbar (Fehler: {e})")

# ==========================================
# TAB 3: NINO
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

        st.markdown("---")
        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
          st.markdown("#### 📊 Performance nach Ticker")
          if (
              "ticker" in df_eval.columns
              and "end_performance_5_tage" in df_eval.columns
          ):
            df_chart = df_eval.set_index("ticker")[
                ["end_performance_5_tage"]
            ].dropna()
            if not df_chart.empty:
              st.bar_chart(df_chart)
        with col_chart2:
          st.markdown("#### 🚀 Max-Peak vs. End-Performance")
          if (
              "max_performance_5_tage" in df_eval.columns
              and "end_performance_5_tage" in df_eval.columns
          ):
            df_comparison = df_eval.set_index("ticker")[
                ["max_performance_5_tage", "end_performance_5_tage"]
            ].dropna()
            if not df_comparison.empty:
              st.line_chart(df_comparison)
      else:
        st.warning("⚠️ Noch keine 5-Tages-Auswertungen vorhanden.")
    else:
      st.info("Das Journal ist komplett leer.")
  except Exception as e:
    st.error(f"Nino-Tab aktuell nicht verfügbar (Fehler: {e})")

# ==========================================
# TAB 4: PETER
# ==========================================
with tab_peter:
  try:
    from employees.peter import PeterInsiderAnalyst

    peter = PeterInsiderAnalyst(supabase)

    st.subheader(f"🕵️ {peter.name}")
    st.caption(peter.description)

    if st.button(
        "🔄 Peter: Markt-Intel & Kennzahlen aktualisieren", key="btn_run_peter"
    ):
      with st.spinner("Peter holt aktuelle Marktdaten..."):
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
        st.info(
            f"**Insider & Aktivität:**\n\n{latest_intel.get('insider_activity')}"
        )
        st.warning(
            f"**Analysten-Konsens /"
            f" Bewertung:**\n\n{latest_intel.get('analyst_consensus')}"
        )
      with col2:
        st.success(
            f"**Markt- & News-Summary:**\n\n{latest_intel.get('market_news_summary')}"
        )
    else:
      st.info("Noch keine Markt-Intel vorhanden.")
  except Exception as e:
    st.error(f"Peter-Tab aktuell nicht verfügbar (Fehler: {e})")

# ==========================================
# TAB 5: ARIS (Performance Manager & Chat)
# ==========================================
with tab_aris:
  st.subheader("🤖 Aris - Performance Manager")
  st.markdown(
      "Dein KI-Agent analysiert das Signals-Journal, das Trading-Journal, "
      "den Screener-Quellcode und steht dir im Chat für Rückfragen zur Verfügung."
  )

  # 1. Session State für den Aris-Chat initialisieren
  if "messages_aris" not in st.session_state:
    st.session_state.messages_aris = []

  aris_dna = """
    Du bist Aris, der leitende Performance Manager in dieser Trading-Anwendung. Deine Aufgabe ist es, die Performance objektiv, datenbasiert und gnadenlos ehrlich zu analysieren. Du verzichtest auf leere Floskeln und Schönfärberei. 
    Analysiere die übergebenen Datenpunkte:
    1. Signals Journal (inkl. 5-Tage und 1-Monats-Meilensteine)
    2. Trading Journal (geschlossene Trades inkl. Post-Exit-Tracking)
    3. Screener-Quellcode (auf Filterfehler, Schwachstellen und verpasste Chancen prüfen)
    4. Watchlist (nach Asset-Kategorien: Invest, Swing, High Risk)

    Finde Muster, vergleiche Gewinner vs. Verlierer, bewerte ob Trades zu früh geschlossen wurden und liefere konkrete, direkt umsetzbare Handlungsempfehlungen. Wenn du Code-Verbesserungen oder eiserne Regeln findest, formuliere sie klar, damit sie in die 'principles_and_insights'-Tabelle übernommen werden können.
    Antworte strukturiert, prägnant und auf den Punkt.
    """

  # 0. Gespeicherten Report aus Supabase laden (falls noch kein Chat da ist)
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

  # Button zum Ausführen der Hauptanalyse
  if st.button(
      "🚀 Aris Analyse & Screener-Review starten",
      type="primary",
      key="run_aris_btn",
      use_container_width=True,
  ):
    with st.spinner(
        "Aris analysiert Datenbanken, liest Screener-Code ein und prüft"
        " Meilensteine mit Gemini..."
    ):
      try:
        api_key = st.secrets["GEMINI_API_KEY"]
        genai.configure(api_key=api_key)

        signals_res = (
            supabase.table("signals_journal")
            .select("*")
            .eq("aris_status_5d", False)
            .execute()
        )
        journal_res = (
            supabase.table("trade_journal")
            .select("*")
            .eq("aris_status_5d", False)
            .execute()
        )
        watchlist_res = supabase.table("watchlist").select("*").execute()

        signals_df = pd.DataFrame(signals_res.data)
        journal_df = pd.DataFrame(journal_res.data)
        watchlist_df = pd.DataFrame(watchlist_res.data)

        # Screener-Code einlesen (Sicherheitsbegrenzung auf 15.000 Zeichen)
        screener_code_content = ""
        try:
          screener_path = Path("screeners/main_screener.py")
          if screener_path.exists():
            screener_code_content = screener_path.read_text(encoding="utf-8")
          else:
            screener_files = list(Path(".").glob("**/*screener*.py"))
            if screener_files:
              screener_code_content = screener_files[0].read_text(
                  encoding="utf-8"
              )
          if len(screener_code_content) > 15000:
            screener_code_content = (
                screener_code_content[:15000]
                + "\n... [Code gekürzt wegen Länge]"
            )
        except Exception as code_err:
          screener_code_content = (
              f"Konnte Screener-Code nicht laden: {code_err}"
          )

        # Post-Exit Tracking
        post_exit_results = []
        if not journal_df.empty and "ausstieg_datum_zeit" in journal_df.columns:
          for _, row in journal_df.head(15).iterrows():
            ticker = row.get("ticker")
            exit_date_str = row.get("ausstieg_datum_zeit")
            exit_price = float(row.get("ausstiegskurs", 0))
            try:
              exit_date = pd.to_datetime(exit_date_str)
              end_date = exit_date + timedelta(days=30)
              df_post = yf.download(
                  ticker,
                  start=exit_date.strftime("%Y-%m-%d"),
                  end=end_date.strftime("%Y-%m-%d"),
                  progress=False,
                  auto_adjust=True,
              )
              if not df_post.empty and "Close" in df_post:
                max_post_price = float(df_post["Close"].max())
                perf_after = (
                    ((max_post_price - exit_price) / exit_price) * 100
                    if exit_price > 0
                    else 0
                )
                post_exit_results.append({
                    "ticker": ticker,
                    "ausstieg_preis": exit_price,
                    "max_preis_30d_danach": max_post_price,
                    "verpasste_bewegung_%": round(perf_after, 2),
                })
            except Exception:
              continue

        # Watchlist Extremwerte
        top_winners, top_losers = [], []
        if not watchlist_df.empty:
          watchlist_df["perf_titel"] = pd.to_numeric(
              watchlist_df.get("performance", 0), errors="coerce"
          )
          sorted_wl = watchlist_df.sort_values(by="perf_titel", ascending=False)
          top_winners = sorted_wl.head(10).to_dict(orient="records")
          top_losers = sorted_wl.tail(10).to_dict(orient="records")

        # Kontext bündeln
        context_data = f"""
            --- SIGNALS JOURNAL ---
            {signals_df.to_string() if not signals_df.empty else "Keine neuen Signale"}

            --- TRADING JOURNAL ---
            {journal_df.to_string() if not journal_df.empty else "Keine offenen Journal-Einträge"}

            --- POST-EXIT TRACKING ---
            {pd.DataFrame(post_exit_results).to_string() if post_exit_results else "Keine Daten"}

            --- SCREENER-QUELLCODE ---
            {screener_code_content if screener_code_content else "Kein Code gefunden"}

            --- WATCHLIST TOP GEWINNER / VERLIERER ---
            Gewinner:\n{pd.DataFrame(top_winners).to_string() if top_winners else "Keine"}
            Verlierer:\n{pd.DataFrame(top_losers).to_string() if top_losers else "Keine"}
            """

        # Gemini Request für den Initial-Report (mit gemini-3.6-flash)
        model = genai.GenerativeModel(
            model_name="gemini-3.6-flash", system_instruction=aris_dna
        )
        response = model.generate_content(
            "Erstelle deinen Analyse-Report basierend auf folgenden Daten:\n\n"
            + context_data
        )

        report_content = response.text

        # In Supabase speichern
        try:
          supabase.table("agent_reports").insert({
              "agent_name": "Aris",
              "report_content": report_content,
          }).execute()
        except Exception:
          pass

        # Status aktualisieren
        if not signals_df.empty and "id" in signals_df.columns:
          supabase.table("signals_journal").update({"aris_status_5d": True}).in_(
              "id", signals_df["id"].tolist()
          ).execute()
        if not journal_df.empty and "id" in journal_df.columns:
          supabase.table("trade_journal").update({"aris_status_5d": True}).in_(
              "id", journal_df["id"].tolist()
          ).execute()

        # Neuen Report direkt als Assistant-Nachricht in den Chat setzen
        st.session_state.messages_aris.append(
            {"role": "assistant", "content": report_content}
        )
        st.success("Analyse erfolgreich abgeschlossen!")
        st.rerun()

      except Exception as e:
        st.error(f"⚠️ Fehler: {e}")

  st.markdown("---")
  st.markdown("### 💬 Diskussion mit Aris")

  # 2. Bestehenden Chatverlauf rendern
  for message in st.session_state.messages_aris:
    with st.chat_message(message["role"]):
      st.markdown(message["content"])

  # 3. Chat-Eingabe für Rückfragen
  if user_query := st.chat_input(
      "Stelle Aris eine Frage zu den Trades oder dem Code..."
  ):
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

          # Verlauf für Gemini formatieren (Sicherstellen, dass er sauber mit 'user' startet)
          gemini_history = []
          for m in st.session_state.messages_aris[:-1]:
            role = "user" if m["role"] == "user" else "model"

            # Verhindern, dass die Historie mit 'model' beginnt (wegen des initialen Reports)
            if not gemini_history and role == "model":
              continue

            gemini_history.append({"role": role, "parts": [m["content"]]})

          # Chat-Modell (gemini-3.6-flash)
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