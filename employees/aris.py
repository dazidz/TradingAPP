from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
from supabase import create_client
import yfinance as yf
from openai import OpenAI

# OpenAI Client initialisieren
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

ARIS_DNA = """
Du bist Aris, der leitende Performance Manager in dieser Trading-Anwendung. Deine Aufgabe ist es, die Performance objektiv, datenbasiert und gnadenlos ehrlich zu analysieren. Du verzichtest auf leere Floskeln und Schönfärberei. 
Analysiere die übergebenen Datenpunkte (Signals Journal, Trading Journal inkl. Post-Exit-Tracking, Watchlist-Tagesextremwerte und Sektoren).
Finde Muster, vergleiche Gewinner vs. Verlierer, bewerte ob Trades zu früh geschlossen wurden und liefere konkrete, direkt umsetzbare Handlungsempfehlungen.
Antworte strukturiert, prägnant und auf den Punkt.
"""

# Beispiel für deinen Team-Seiten Tab (z.B. tab_aris)
# tab_team, tab_aris = st.tabs(["👥 Team Übersicht", "🤖 Aris Performance Manager"])

# with tab_aris:
st.subheader("🤖 Aris - Performance Manager")
st.markdown(
    "Dein KI-Agent analysiert das Signals-Journal, das Trading-Journal"
    " (inklusive 30-Tage-Post-Exit-Tracking), die Watchlist-Extremwerte und"
    " Sektoren."
)

if st.button(
    "🚀 Aris Tages-Analyse starten",
    type="primary",
    key="run_aris_btn",
    use_container_width=True,
):
  with st.spinner(
      "Aris analysiert Datenbanken und zieht Post-Exit-Kursdaten über"
      " yfinance..."
  ):
    try:
      # 1. Daten aus Supabase laden
      signals_res = supabase.table("signals").select("*").execute()
      journal_res = supabase.table("trade_journal").select("*").execute()
      watchlist_res = supabase.table("watchlist").select("*").execute()

      signals_df = pd.DataFrame(signals_res.data)
      journal_df = pd.DataFrame(journal_res.data)
      watchlist_df = pd.DataFrame(watchlist_res.data)

      # 2. Post-Exit Tracking (30 Tage nach Trade-Schluss)
      post_exit_results = []
      if not journal_df.empty and "ausstieg_datum_zeit" in journal_df.columns:
        for _, row in journal_df.head(20).iterrows():
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

      # 3. Watchlist Extremwerte (Top 10 Gewinner / Verlierer)
      top_winners, top_losers = [], []
      if not watchlist_df.empty:
        watchlist_df["perf_titel"] = pd.to_numeric(
            watchlist_df.get("performance", 0), errors="coerce"
        )
        sorted_wl = watchlist_df.sort_values(by="perf_titel", ascending=False)
        top_winners = sorted_wl.head(10).to_dict(orient="records")
        top_losers = sorted_wl.tail(10).to_dict(orient="records")

      # 4. Datenkontext für OpenAI bündeln
      context_data = f"""
            --- SIGNALS JOURNAL ---
            {signals_df.to_string() if not signals_df.empty else "Keine Daten"}

            --- TRADING JOURNAL (GESCHLOSSENE TRADES) ---
            {journal_df.to_string() if not journal_df.empty else "Keine Daten"}

            --- POST-EXIT TRACKING (30 Tage nach Verkauf) ---
            {pd.DataFrame(post_exit_results).to_string() if post_exit_results else "Keine Daten"}

            --- WATCHLIST TOP 10 GEWINNER ---
            {pd.DataFrame(top_winners).to_string() if top_winners else "Keine Daten"}

            --- WATCHLIST TOP 10 VERLIERER ---
            {pd.DataFrame(top_losers).to_string() if top_losers else "Keine Daten"}
            """

      # 5. Anfrage an OpenAI
      response = client.chat.completions.create(
          model="gpt-4o",
          messages=[
              {"role": "system", "content": ARIS_DNA},
              {
                  "role": "user",
                  "content": (
                      "Hier sind die aktuellen Performance-Daten des Systems."
                      " Erstelle deinen täglichen Analyse-Report:\n\n"
                      + context_data
                  ),
              },
          ],
          temperature=0.3,
      )

      st.markdown("### 📊 Aris' Performance-Report")
      st.markdown(response.choices[0].message.content)

    except Exception as e:
      st.warning(
        "🤖 Aris befindet sich aktuell im Aufbau (DNA wird definiert). Die"
        f" anderen Tabs funktionieren einwandfrei. (Fehler: {e})"
    )