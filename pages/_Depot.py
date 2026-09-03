import streamlit as st
from supabase import create_client
import pandas as pd
import yfinance as yf
from datetime import datetime

st.set_page_config(layout="wide", page_title="VisionDZ - Depot & Journal", page_icon="📈")

if not st.session_state.get("password_correct", False):
    st.warning("Bitte melde dich zuerst auf der Hauptseite an.")
    st.stop()

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

st.title("📈 VisionDZ - Depot & Trading Journal")
st.markdown("Verwaltung der separarten Depot-Tabellen und lückenlose Dokumentation aller Trades.")

tab_depot, tab_journal, tab_new_trade = st.tabs(["💼 Depots (Invest / Swing / Risiko)", "📖 Trading Journal", "➕ Neuer Trade"])

# Mapping von UI-Namen zu den exakten Supabase-Tabellennamen
depot_tables = {
    "Invest Depot": "invest_depot",
    "Swing Depot": "swing_depot",
    "Risiko Depot": "risk_depot"
}

# ==========================================
# TAB 1: DIE DEPOTS
# ==========================================
with tab_depot:
    st.subheader("Aktive Positionen nach Strategie-Depot")
    
    # Depot-Auswahl über Radio-Buttons oder Selectbox
    selected_depot_ui = st.radio(
        "Wähle das Depot:",
        list(depot_tables.keys()),
        horizontal=True
    )
    
    target_table = depot_tables[selected_depot_ui]
    st.markdown(f"**Aktive Tabelle in Supabase:** `{target_table}`")

    try:
        response = supabase.table(target_table).select("*").execute()
        positions = response.data

        if positions:
            df_pos = pd.DataFrame(positions)
            
            # Live-Preise über yfinance holen
            tickers = df_pos['ticker'].unique().tolist()
            live_prices = {}
            if tickers:
                df_hist = yf.download(tickers, period="1d", progress=False, auto_adjust=True)
                for t in tickers:
                    try:
                        if len(tickers) == 1:
                            live_prices[t] = float(df_hist['Close'].iloc[-1])
                        else:
                            live_prices[t] = float(df_hist['Close'][t].iloc[-1])
                    except Exception:
                        live_prices[t] = 0.0

            portfolio_data = []
            total_value = 0
            total_invested = 0

            for _, row in df_pos.iterrows():
                ticker = row['ticker']
                shares = float(row['shares'])
                buy_price = float(row['buy_price'])
                curr_price = live_prices.get(ticker, buy_price)
                
                inv_val = shares * buy_price
                curr_val = shares * curr_price
                pnl = curr_val - inv_val
                pnl_pct = (pnl / inv_val) * 100 if inv_val > 0 else 0

                total_invested += inv_val
                total_value += curr_val

                portfolio_data.append({
                    "ID": row['id'],
                    "Ticker": ticker,
                    "Anteile": shares,
                    "Kaufpreis (€)": f"{buy_price:.2f}",
                    "Aktuell (€)": f"{curr_price:.2f}",
                    "Gesamtwert (€)": f"{curr_val:.2f}",
                    "P&L (€)": f"{pnl:+.2f}",
                    "P&L (%)": f"{pnl_pct:+.2f}%"
                })

            total_pnl = total_value - total_invested
            total_pnl_pct = (total_pnl / total_invested) * 100 if total_invested > 0 else 0

            m1, m2, m3 = st.columns(3)
            m1.metric("Gesamtwert Depot", f"{total_value:,.2f} €")
            m2.metric("Gesamtes Invest", f"{total_invested:,.2f} €")
            m3.metric("Gesamt-P&L", f"{total_pnl:+.2f} €", f"{total_pnl_pct:+.2f}%")

            st.divider()

            df_display = pd.DataFrame(portfolio_data)
            st.dataframe(df_display.drop(columns=["ID"]), use_container_width=True)

        else:
            st.info(f"Keine offenen Positionen im `{selected_depot_ui}` vorhanden.")

    except Exception as e:
        st.error(f"Fehler beim Laden von `{target_table}`: {e}")

# ==========================================
# TAB 2: DAS TRADING JOURNAL
# ==========================================
with tab_journal:
    st.subheader("Historisches Trade Journal")
    st.markdown("Chronologische Aufzeichnung aller Transaktionen aus der Tabelle `trade_journal`.")

    try:
        res_journal = supabase.table("trade_journal").select("*").order("trade_date", desc=True).execute()
        journal_data = res_journal.data

        if journal_data:
            df_j = pd.DataFrame(journal_data)
            st.dataframe(df_j, use_container_width=True)
        else:
            st.info("Das Journal ist noch leer.")
    except Exception as e:
        st.error(f"Fehler beim Laden von `trade_journal`: {e}")

# ==========================================
# TAB 3: NEUEN TRADE ERFASSEN
# ==========================================
with tab_new_trade:
    st.subheader("➕ Transaktion erfassen & Depot zuweisen")
    
    with st.form("trade_form"):
        col_t1, col_t2 = st.columns(2)
        
        with col_t1:
            t_ticker = st.text_input("Ticker-Symbol (z.B. AAPL, GC=F)").upper()
            t_action = st.selectbox("Aktion", ["BUY", "SELL"])
            t_target_depot = st.selectbox("Ziel-Depot", list(depot_tables.keys()))
        
        with col_t2:
            t_shares = st.number_input("Anzahl Anteile", min_value=0.0001, value=1.0, format="%.4f")
            t_price = st.number_input("Ausführungspreis pro Einheit (€)", min_value=0.01, value=100.0, format="%.2f")
        
        t_reason = st.text_area("Begründung / Kausalität (Bezug auf Team-Standup):", placeholder="Z.B.: 'Basierend auf Ottos Makro-Analyse im Invest-Depot aufgebaut...'")
        
        submitted = st.form_submit_button("Trade ausführen & speichern")
        
        if submitted:
            if t_ticker:
                try:
                    now_str = datetime.now().isoformat()
                    dest_table = depot_tables[t_target_depot]
                    
                    # 1. Immer ins zentrale Journal eintragen
                    supabase.table("trade_journal").insert({
                        "ticker": t_ticker,
                        "action": t_action,
                        "shares": t_shares,
                        "price": t_price,
                        "reason": f"[{t_target_depot}] {t_reason}",
                        "trade_date": now_str
                    }).execute()

                    # 2. Wenn BUY, in die entsprechende Depot-Tabelle einfügen
                    if t_action == "BUY":
                        supabase.table(dest_table).insert({
                            "ticker": t_ticker,
                            "shares": t_shares,
                            "buy_price": t_price,
                            "buy_date": now_str
                        }).execute()
                    
                    st.success(f"Trade erfolgreich in `trade_journal` und `{dest_table}` verankert!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Fehler beim Speichern: {e}")
            else:
                st.warning("Bitte gib ein Ticker-Symbol ein.")