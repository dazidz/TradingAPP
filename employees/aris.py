from datetime import datetime, timedelta
from pathlib import Path
import os
from groq import Groq
import pandas as pd
import streamlit as st
from supabase import create_client
import yfinance as yf

# Groq Client / API Key initialisieren
try:
    groq_api_key = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")

    if not groq_api_key:
        raise ValueError(
            "Kein Groq API-Key gefunden. Bitte in den Streamlit Secrets oder als"
            " Environment Variable hinterlegen."
        )

    groq_client = Groq(api_key=groq_api_key)
except Exception as e:
    st.error(
        "Fehler beim Initialisieren des Groq Clients:" f" {e}"
    )

ARIS_DNA = """
Du bist Aris, der leitende Performance Manager in dieser Trading-Anwendung. Deine Aufgabe ist es, die Performance objektiv, datenbasiert und gnadenlos ehrlich zu analysieren. Du verzichtest auf leere Floskeln und Schönfärberei. 
Analysiere die übergebenen Kennzahlen und Zusammenfassungen:
1. Signals Journal (Performance nach 5/30 Tagen)
2. Trading Journal (Geschlossene Trades & Post-Exit-Tracking)
3. Joris Journal (Swing-Setups)
4. Watchlist & Top/Flop Performance

Finde Muster, vergleiche Gewinner vs. Verlierer, bewerte ob Trades zu früh geschlossen wurden und liefere konkrete, direkt umsetzbare Handlungsempfehlungen.
Antworte strukturiert, prägnant und auf den Punkt.
"""

st.subheader("🤖 Aris - Performance Manager")
st.markdown(
    "Dein KI-Agent analysiert aggregierte Journal-Daten und liefert präzise Performance-Insights."
)

# 1. Session State für den Aris-Chat initialisieren
if "messages_aris" not in st.session_state:
    st.session_state.messages_aris = []

# 0. Gespeicherten Report aus Supabase laden (falls noch kein Chat da ist)
try:
    saved_report_res = (
        supabase.table("agent_reports")
        .select("*")
        .eq("agent_name", "Aris")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if saved_report_res.data and not st.session_state.messages_aris:
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
    "🚀 Aris Performance-Analyse starten",
    type="primary",
    key="run_aris_btn",
    use_container_width=True,
):
    with st.spinner("Aris verdichtet Daten und analysiert die Performance mit Groq..."):
        try:
            # --- Datenabfrage: Nur ungeprüfte (False), bei denen die 5-Tage-Performance bereits berechnet wurde ---
            signals_res = (
                supabase.table("signals_journal")
                .select("id, ticker, signal_typ, einstiegspreis_zum_signal, max_performance_5_tage, performance_30d_end_pct, aris_status_5d")
                .eq("aris_status_5d", False)
                .not_.is_("max_performance_5_tage", "null")
                .execute()
            )
            
            journal_res = (
                supabase.table("trading_journal")
                .select("id, ticker, ausstiegskurs, ausstieg_datum_zeit, max_performance_5_tage, performance_30d_end_pct, aris_status_5d")
                .eq("aris_status_5d", False)
                .not_.is_("max_performance_5_tage", "null")
                .execute()
            )

            watchlist_res = supabase.table("watchlist").select("ticker, performance, kategorie").execute()
            
            joris_journal_res = (
                supabase.table("joris_journal")
                .select("id, ticker, signal_typ, status, max_performance_5_tage, performance_30d_end_pct")
                .not_.is_("max_performance_5_tage", "null")
                .execute()
            )

            signals_df = pd.DataFrame(signals_res.data)
            journal_df = pd.DataFrame(journal_res.data)
            watchlist_df = pd.DataFrame(watchlist_res.data)
            joris_journal_df = pd.DataFrame(joris_journal_res.data)

            # Prüfen ob überhaupt neue Daten zum Auswerten da sind
            if signals_df.empty and journal_df.empty and joris_journal_df.empty:
                st.info("ℹ️ Keine neuen, fertig getrackten Datensätze für Aris vorhanden (alle bereits geprüft oder noch in der Wartezeit).")
            else:
                # Kompakte Übergabe der echten Performance-Werte an Aris
                sig_summary = signals_df[["ticker", "signal_typ", "max_performance_5_tage", "performance_30d_end_pct"]].to_string(index=False) if not signals_df.empty else "Keine neuen Signale zur Bewertung."
                trade_summary = journal_df[["ticker", "max_performance_5_tage", "performance_30d_end_pct"]].to_string(index=False) if not journal_df.empty else "Keine neuen Trades zur Bewertung."
                joris_summary = joris_journal_df[["ticker", "signal_typ", "status", "max_performance_5_tage"]].to_string(index=False) if not joris_journal_df.empty else "Keine Joris-Einträge mit Performance vorhanden."

                # Watchlist Top/Flop Extremwerte filtern
                top_winners, top_losers = [], []
                if not watchlist_df.empty:
                    watchlist_df["perf_titel"] = pd.to_numeric(watchlist_df.get("performance", 0), errors="coerce")
                    sorted_wl = watchlist_df.sort_values(by="perf_titel", ascending=False)
                    top_winners = sorted_wl.head(5)[["ticker", "perf_titel"]].to_dict(orient="records")
                    top_losers = sorted_wl.tail(5)[["ticker", "perf_titel"]].to_dict(orient="records")

                context_data = f"""
                --- SIGNALS JOURNAL (Bereits nach 5D/30D getrackt, ungeprüft durch Aris) ---
                {sig_summary}

                --- TRADING JOURNAL (Post-Exit Tracking, ungeprüft durch Aris) ---
                {trade_summary}

                --- JORIS JOURNAL (Swing-Setups mit Performance) ---
                {joris_summary}

                --- WATCHLIST TOP 5 GEWINNER ---
                {top_winners}

                --- WATCHLIST TOP 5 VERLIERER ---
                {top_losers}
                """

                # Groq Request
                completion = groq_client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=[
                        {"role": "system", "content": ARIS_DNA},
                        {
                            "role": "user",
                            "content": (
                                "Erstelle deinen kompakten Performance-Report basierend auf diesen komprimierten Kennzahlen:\n\n"
                                + context_data
                            ),
                        },
                    ],
                    temperature=0.1,
                )

                report_content = completion.choices[0].message.content

                # In Supabase speichern
                try:
                    supabase.table("agent_reports").insert({
                        "agent_name": "Aris",
                        "report_content": report_content,
                    }).execute()
                except Exception:
                    pass

                # Status in Supabase auf True aktualisieren (damit sie nicht doppelt geprüft werden)
                if not signals_df.empty and "id" in signals_df.columns:
                    supabase.table("signals_journal").update({"aris_status_5d": True}).in_(
                        "id", signals_df["id"].tolist()
                    ).execute()
                if not journal_df.empty and "id" in journal_df.columns:
                    supabase.table("trading_journal").update({"aris_status_5d": True}).in_(
                        "id", journal_df["id"].tolist()
                    ).execute()

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

if user_query := st.chat_input(
    "Stelle Aris eine Frage zu den Trades..."
):
    st.session_state.messages_aris.append(
        {"role": "user", "content": user_query}
    )
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        with st.spinner("Aris denkt nach..."):
            try:
                groq_history = [
                    {"role": "system", "content": ARIS_DNA},
                    {
                        "role": "system",
                        "content": (
                            "PROJEKT-KONTEXT & FOKUS: Du bist datenbasierter Performance Manager. "
                            "Achte auf saubere Logik, striktes Risk-Management und optimiere die Trading-Performance."
                        ),
                    },
                ]

                # Nur die letzten maximal 6 Nachrichten mitnehmen
                MAX_HISTORY = 6
                recent_messages = st.session_state.messages_aris[-MAX_HISTORY:]

                for m in recent_messages:
                    content = m["content"]
                    if "**Letzter gespeicherter Report" in content or len(content) > 1000:
                        content = "[System-Hinweis: Vorheriger Report wurde komprimiert.]"

                    role = "user" if m["role"] == "user" else "assistant"
                    groq_history.append({"role": role, "content": content})

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