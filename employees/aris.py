from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import streamlit as st
from supabase import create_client
import yfinance as yf
from openai import OpenAI

# OpenAI Client initialisieren
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

ARIS_DNA = """
Du bist Aris, der leitende Performance Manager in dieser Trading-Anwendung. Deine Aufgabe ist es, die Performance objektiv, datenbasiert und gnadenlos ehrlich zu analysieren. Du verzichtest auf leere Floskeln und Schönfärberei. 
Analysiere die übergebenen Datenpunkte:
1. Signals Journal (inkl. 5-Tage und 1-Monats-Meilensteine)
2. Trading Journal (geschlossene Trades inkl. Post-Exit-Tracking)
3. Screener-Quellcode (auf Filterfehler, Schwachstellen und verpasste Chancen prüfen)
4. Watchlist (nach Asset-Kategorien: Invest, Swing, High Risk)

Finde Muster, vergleiche Gewinner vs. Verlierer, bewerte ob Trades zu früh geschlossen wurden und liefere konkrete, direkt umsetzbare Handlungsempfehlungen. Wenn du Code-Verbesserungen oder eiserne Regeln findest, formuliere sie klar, damit sie in die 'principles_and_insights'-Tabelle übernommen werden können.
Antworte strukturiert, prägnant und auf den Punkt.
"""

st.subheader("🤖 Aris - Performance Manager")
st.markdown(
    "Dein KI-Agent analysiert das Signals-Journal, das Trading-Journal, "
    "den Screener-Quellcode und das 5-Tage-/1-Monats-Tracking."
)

# 0. Gespeicherten Report aus Supabase laden (falls vorhanden)
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
    st.info(
        f"Letzter gespeicherter Report vom: {latest_report['created_at'][:16]}"
    )
    with st.expander("📄 Letzten Bericht anzeigen", expanded=False):
      st.markdown(latest_report["report_content"])
except Exception:
  pass

if st.button(
    "🚀 Aris Analyse & Screener-Review starten",
    type="primary",
    key="run_aris_btn",
    use_container_width=True,
):
  with st.spinner(
      "Aris analysiert Datenbanken, liest Screener-Code ein und prüft Meilensteine..."
  ):
    try:
      # 1. Daten aus Supabase laden
      signals_res = (
          supabase.table("signals_journal")
          .select("*")
          .eq("aris_status_5d", False)
          .execute()
      )
      journal_res = (
          supabase.table("trading_journal")
          .select("*")
          .eq("aris_status_5d", False)
          .execute()
      )
      watchlist_res = supabase.table("watchlist").select("*").execute()

      signals_df = pd.DataFrame(signals_res.data)
      journal_df = pd.DataFrame(journal_res.data)
      watchlist_df = pd.DataFrame(watchlist_res.data)

      # 2. Screener-Code einlesen (Beispielhafter Pfad zu deinen Screenern)
      screener_code_content = ""
      try:
        # Passe den Pfad an, je nachdem wo deine Screener liegen (z.B. folder 'screeners/')
        screener_path = Path("screeners/main_screener.py")
        if screener_path.exists():
          screener_code_content = screener_path.read_text(encoding="utf-8")
        else:
          # Fallback, falls die Datei anders heißt oder woanders liegt
          screener_files = list(Path(".").glob("**/*screener*.py"))
          if screener_files:
            screener_code_content = screener_files[0].read_text(encoding="utf-8")
      except Exception as code_err:
        screener_code_content = (
            f"Konnte Screener-Code nicht laden: {code_err}"
        )

      # 3. Post-Exit / Meilenstein Tracking (5 Tage & 1 Monat)
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

      # 4. Watchlist Extremwerte nach Asset-Kategorie
      top_winners, top_losers = [], []
      if not watchlist_df.empty:
        watchlist_df["perf_titel"] = pd.to_numeric(
            watchlist_df.get("performance", 0), errors="coerce"
        )
        sorted_wl = watchlist_df.sort_values(by="perf_titel", ascending=False)
        top_winners = sorted_wl.head(10).to_dict(orient="records")
        top_losers = sorted_wl.tail(10).to_dict(orient="records")

      # 5. Datenkontext für OpenAI bündeln
      context_data = f"""
            --- SIGNALS JOURNAL (Offene/Zu prüfende Meilensteine) ---
            {signals_df.to_string() if not signals_df.empty else "Keine neuen Signale"}

            --- TRADING JOURNAL (Trades für 5T / 1M Meilenstein-Check) ---
            {journal_df.to_string() if not journal_df.empty else "Keine offenen Journal-Einträge"}

            --- POST-EXIT TRACKING (30 Tage nach Verkauf) ---
            {pd.DataFrame(post_exit_results).to_string() if post_exit_results else "Keine Daten"}

            --- AKTUELLER SCREENER-QUELLCODE (Zur Code-Optimierung) ---
            {screener_code_content if screener_code_content else "Kein Screener-Code gefunden"}

            --- WATCHLIST TOP 10 GEWINNER & ASSET-KATEGORIEN ---
            {pd.DataFrame(top_winners).to_string() if top_winners else "Keine Daten"}

            --- WATCHLIST TOP 10 VERLIERER ---
            {pd.DataFrame(top_losers).to_string() if top_losers else "Keine Daten"}
            """

      # 6. Anfrage an OpenAI
      response = client.chat.completions.create(
          model="gpt-4o",
          messages=[
              {"role": "system", "content": ARIS_DNA},
              {
                  "role": "user",
                  "content": (
                      "Hier sind die aktuellen Daten und der Screener-Quellcode."
                      " Führe deinen Analyse-Report durch, prüfe die"
                      " 5-Tage/1-Monats-Meilensteine sowie den Screener-Code"
                      " auf Verbesserungspotenzial:\n\n"
                      + context_data
                  ),
              },
          ],
          temperature=0.3,
      )

      report_content = response.choices[0].message.content

      # 7. Bericht in Supabase (Tabelle agent_reports) speichern
      try:
        supabase.table("agent_reports").insert({
            "agent_name": "Aris",
            "report_content": report_content,
        }).execute()
      except Exception as db_save_err:
        st.warning(f"Konnte Report nicht in Supabase sichern: {db_save_err}")

      # 8. Status in den Tabellen aktualisieren, damit sie nicht doppelt laufen
      if not signals_df.empty and "id" in signals_df.columns:
        signal_ids = signals_df["id"].tolist()
        supabase.table("signals_journal").update({"aris_status_5d": True}).in_(
            "id", signal_ids
        ).execute()

      if not journal_df.empty and "id" in journal_df.columns:
        journal_ids = journal_df["id"].tolist()
        supabase.table("trading_journal").update({"aris_status_5d": True}).in_(
            "id", journal_ids
        ).execute()

      st.markdown("### 📊 Aris' frischer Performance-Report")
      st.markdown(report_content)

    except Exception as e:
      st.error(f"⚠️ Aris-Fehler im Detail: {e}")