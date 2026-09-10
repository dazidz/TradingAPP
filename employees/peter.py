from datetime import datetime, timedelta
import os
from pathlib import Path
from groq import Groq
import pandas as pd
import streamlit as st
from supabase import create_client
import yfinance as yf


class PeterInsiderAnalyst:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.name = "Peter"
    self.description = (
        "Micro- & Insider-Analyst für Live-Daten und Markt-Anomalien."
    )
    self.init_error = None
    self.groq_client = None

    api_key = self._find_api_key()
    if api_key:
      try:
        self.groq_client = Groq(api_key=api_key)
      except Exception as e:
        self.init_error = e

    self.peter_dna = """
        Du bist Peter, der Micro- & Insider-Analyst in dieser Trading-Anwendung. Deine Aufgabe ist es, Live-Daten, Marktnachrichten, Insider-Aktivitäten und Mikro-Faktoren objektiv und präzise zu analysieren. Du verzichtest auf leere Floskeln und Schönfärberei. 
        Analysiere die übergebenen Live-Daten und News-Ausschnitte. Finde Anomalien, Insider-Käufe/-Verkäufe, Sentiment-Verschiebungen und liefere konkrete, direkt umsetzbare Erkenntnisse.
        Antworte strukturiert, prägnant und auf den Punkt.
        """

  def _find_api_key(self, provided_key: str = None):
    if provided_key:
      return provided_key
    
    for key_name in ["GROQ_API_KEY", "groq_api_key", "Groq_API_Key"]:
      try:
        val = st.secrets.get(key_name)
        if val:
          return val
      except Exception:
        pass

    for key_name in ["GROQ_API_KEY", "groq_api_key"]:
      val = os.getenv(key_name)
      if val:
        return val

    return None

  def get_latest_report(self):
    try:
      res = (
          self.supabase.table("agent_reports")
          .select("*")
          .eq("agent_name", "Peter")
          .order("created_at", desc=True)
          .limit(1)
          .execute()
      )
      return res.data[0] if res.data else None
    except Exception:
      return None

  def run_analysis(self, api_key: str = None):
    try:
      active_key = self._find_api_key(api_key)
      if not active_key:
        return False, "Kein Groq API-Key gefunden. Bitte in den Streamlit Secrets als GROQ_API_KEY hinterlegen."

      client = Groq(api_key=active_key)

      signals_res = self.supabase.table("signals").select("*").execute()

      if not signals_res.data:
        return False, "Keine Einträge in der 'signals'-Tabelle gefunden."

      df_signals = pd.DataFrame(signals_res.data)

      if "signal_type" not in df_signals.columns or "ticker" not in df_signals.columns:
        return False, "Spalten 'signal_type' oder 'ticker' fehlen in der signals-Tabelle."

      elite_df = df_signals[
          df_signals["signal_type"].str.contains("elite", case=False, na=False)
      ].copy()

      if elite_df.empty:
        return False, "Keine Elite-Signale in der signals-Tabelle gefunden."

      filtered_market_data = []

      for _, row in elite_df.iterrows():
        ticker = row["ticker"]
        candle_time = row.get("candle_time")

        try:
          ticker_obj = yf.Ticker(ticker)
          
          todays_data = ticker_obj.history(period="1d")
          if todays_data.empty:
            continue
          current_price = float(todays_data["Close"].iloc[-1])

          entry_price = current_price
          if candle_time:
            hist_candle = ticker_obj.history(start=str(candle_time)[:10], period="2d")
            if not hist_candle.empty:
              entry_price = float(hist_candle["Close"].iloc[0])

          perf_pct = ((current_price - entry_price) / entry_price) * 100

          if abs(perf_pct) <= 1.0:
            filtered_market_data.append({
                "ticker": ticker,
                "signal_type": row["signal_type"],
                "candle_time": str(candle_time),
                "entry_price": round(entry_price, 2),
                "current_price": round(current_price, 2),
                "performance_pct": round(perf_pct, 2)
            })
        except Exception:
          continue

      if not filtered_market_data:
        return False, "Keine Elite-Ticker gefunden, deren aktuelle Performance bei <= 1% liegt."

      context_data = f"""
          --- KONSOLIDIERENDE ELITE-TICKER (Performance <= 1% seit Signal) ---
          {pd.DataFrame(filtered_market_data).to_string()}
          """

      completion = client.chat.completions.create(
          model="llama-3.1-8b-instant",
          messages=[
              {"role": "system", "content": self.peter_dna},
              {
                  "role": "user",
                  "content": (
                      "Analysiere diese konsolidierenden Elite-Ticker (Performance <= 1% seit Signal) "
                      f"auf potenzielle Katalysatoren, News, Insider-Käufe oder 13F-Filings:\n\n{context_data}"
                  ),
              },
          ],
          temperature=0.1,
      )

      report_content = completion.choices[0].message.content

      try:
        self.supabase.table("agent_reports").insert({
            "agent_name": "Peter",
            "report_content": report_content,
        }).execute()
      except Exception:
        pass

      return True, report_content
    except Exception as e:
      return False, f"Fehler bei Peters Analyse: {e}"

  def render_ui(self):
    st.subheader("🤖 Peter - Micro & Insider Analyst")
    st.markdown(
        "Dein KI-Agent analysiert Live-Daten, News und Insider-Aktivitäten "
        "und steht dir im Chat für Rückfragen zur Verfügung."
    )

    if "messages_peter" not in st.session_state:
      st.session_state.messages_peter = []

    try:
      latest_report = self.get_latest_report()
      if latest_report and not st.session_state.messages_peter:
        st.session_state.messages_peter.append({
            "role": "assistant",
            "content": (
                "**Letzter gespeicherter Report ("
                f"{latest_report['created_at'][:16]}):**\n\n"
                + latest_report["report_content"]
            ),
        })
    except Exception:
      pass

    if st.button(
        "🚀 Peter Live-Analyse starten",
        type="primary",
        key="run_peter_btn",
        use_container_width=True,
    ):
      with st.spinner(
          "Peter ruft Live-Daten ab und analysiert mit Groq..."
      ):
        success, result = self.run_analysis()
        if success:
          st.session_state.messages_peter.append(
              {"role": "assistant", "content": result}
          )
          st.success("Analyse erfolgreich abgeschlossen!")
          st.rerun()
        else:
          st.error(f"⚠️ {result}")

    st.markdown("---")
    st.markdown("### 💬 Diskussion mit Peter")

    for message in st.session_state.messages_peter:
      with st.chat_message(message["role"]):
        st.markdown(message["content"])

    if user_query := st.chat_input(
        "Stelle Peter eine Frage zu Live-Daten oder News...",
        key="chat_input_peter",
    ):
      st.session_state.messages_peter.append(
          {"role": "user", "content": user_query}
      )
      with st.chat_message("user"):
        st.markdown(user_query)

      with st.chat_message("assistant"):
        with st.spinner("Peter denkt nach..."):
          try:
            active_key = self._find_api_key()
            if not active_key:
              st.error("Kein Groq API-Key für den Chat verfügbar.")
              return

            chat_client = Groq(api_key=active_key)

            groq_history = [{"role": "system", "content": self.peter_dna}]
            for m in st.session_state.messages_peter[:-1]:
              role = "user" if m["role"] == "user" else "assistant"
              groq_history.append({"role": role, "content": m["content"]})

            completion = chat_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=groq_history,
                temperature=0.1,
            )

            answer = completion.choices[0].message.content
            st.markdown(answer)  

            st.session_state.messages_peter.append(
                {"role": "assistant", "content": answer}
            )
          except Exception as chat_err:
            st.error(f"Fehler im Chat: {chat_err}")