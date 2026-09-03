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
st.markdown("Live-Überwachung der Portfolios und lückenloses Journal geschlossener Trades nach Dalio-Prinzipien.")

tab_depot, tab_journal, tab_new_trade = st.tabs(["💼 Offene Depots", "📖 Trade Journal (Geschlossen)", "➕ Position eröffnen / schließen"])

depot_tables = {
    "Invest Depot": "invest_depot",
    "Swing Depot": "swing_depot",
    "Risiko Depot": "risk_depot"
}

# ==========================================
# TAB 1: DIE AKTIVEN DEPOTS
# ==========================================
with tab_depot:
    st.subheader("Aktive, offene Positionen & Live-Marktwerte")
    
    selected_depot_ui = st.radio(
        "Wähle das Depot:",
        list(depot_tables.keys()),
        horizontal=True,
        key="depot_radio"
    )
    
    target_table = depot_tables[selected_depot_ui]

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
                shares = float(row['anzahl'])
                buy_price = float(row['buy_price'])
                curr_price = live_prices.get(ticker, buy_price)
                
                inv_val = shares * buy_price
                curr_val = shares * curr_price
                pnl_pct = ((curr_price - buy_price) / buy_price) * 100 if buy_price > 0 else 0

                total_invested += inv_val
                total_value += curr_val

                # Live-Werte in Supabase aktualisieren
                try:
                    supabase.table(target_table).update({
                        "live_kurs": curr_price,
                        "gesamtwert": curr_val,
                        "performance": pnl_pct
                    }).eq("id", row['id']).execute()
                except Exception:
                    pass

                portfolio_data.append({
                    "ID": row['id'],
                    "Ticker": ticker,
                    "Datum Einstieg": row.get('datum_einstieg', 'N/A'),
                    "Anzahl": shares,
                    "Kaufpreis (€)": f"{buy_price:.2f}",
                    "Live-Kurs (€)": f"{curr_price:.2f}",
                    "Gesamtwert (€)": f"{curr_val:.2f}",
                    "Performance (%)": f"{pnl_pct:+.2f}%"
                })

            total_pnl = total_value - total_invested
            total_pnl_pct = (total_pnl / total_invested) * 100 if total_invested > 0 else 0

            m1, m2, m3 = st.columns(3)
            m1.metric("Gesamtwert Depot", f"{total_value:,.2f} €")
            m2.metric("Gesamtes Invest", f"{total_invested:,.2f} €")
            m3.metric("Gesamt-Performance", f"{total_pnl:+.2f} €", f"{total_pnl_pct:+.2f}%")

            st.divider()

            df_display = pd.DataFrame(portfolio_data)
            st.dataframe(df_display.drop(columns=["ID"]), use_container_width=True)

        else:
            st.info(f"Keine offenen Positionen im `{selected_depot_ui}` vorhanden.")

    except Exception as e:
        st.error(f"Fehler beim Laden von `{target_table}`: {e}")

# ==========================================
# TAB 2: DAS TRADING JOURNAL (GESCHLOSSENE TRADES)
# ==========================================
with tab_journal:
    st.subheader("Geschlossene Trades & Performance-Historie")
    st.markdown("Chronologische Aufzeichnung mit Einstiegs-, Ausstiegsdaten und finaler Notiz.")

    try:
        res_journal = supabase.table("trade_journal").select("*").order("ausstieg_datum_zeit", desc=True).execute()
        journal_data = res_journal.data

        if journal_data:
            df_j = pd.DataFrame(journal_data)
            st.dataframe(df_j.drop(columns=["id"]), use_container_width=True)
        else:
            st.info("Noch keine geschlossenen Trades im Journal erfasst.")
    except Exception as e:
        st.error(f"Fehler beim Laden des Journals: {e}")

# ==========================================
# TAB 3: POSITION ERÖFFNEN ODER SCHLIESSEN
# ==========================================
with tab_new_trade:
    action_mode = st.radio("Aktion wählen:", ["Neue Position kaufen (BUY)", "Bestehende Position schließen (SELL)"], horizontal=True)
    st.divider()

    if action_mode == "Neue Position kaufen (BUY)":
        st.subheader("➕ Neue Position im Depot eröffnen")
        
        with st.form("buy_form"):
            col_b1, col_b2 = st.columns(2)
            
            with col_b1:
                b_ticker = st.text_input("Ticker-Symbol (z.B. AAPL, GC=F)").upper()
                b_depot = st.selectbox("Ziel-Depot", list(depot_tables.keys()), key="buy_depot")
            
            with col_b2:
                b_shares = st.number_input("Anzahl", min_value=0.0001, value=1.0, format="%.4f", key="buy_shares")
                b_price = st.number_input("Kaufpreis pro Einheit (€)", min_value=0.01, value=100.0, format="%.2f", key="buy_price")
            
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                b_date = st.date_input("Einstiegsdatum", value="today", key="buy_date")
            with col_d2:
                b_time = st.time_input("Einstiegszeit", value=datetime.now().time(), key="buy_time")
            
            submitted_buy = st.form_submit_button("Position in Depot aufnehmen")
            
            if submitted_buy:
                if b_ticker:
                    try:
                        b_timestamp = datetime.combine(b_date, b_time).isoformat()
                        target_tbl = depot_tables[b_depot]
                        
                        initial_val = b_shares * b_price
                        
                        supabase.table(target_tbl).insert({
                            "ticker": b_ticker,
                            "datum_einstieg": b_timestamp,
                            "anzahl": b_shares,
                            "buy_price": b_price,
                            "live_kurs": b_price,
                            "gesamtwert": initial_val,
                            "performance": 0.0
                        }).execute()
                        
                        st.success(f"Position {b_ticker} erfolgreich in `{b_depot}` eröffnet!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Fehler beim Speichern: {e}")
                else:
                    st.warning("Bitte Ticker eingeben.")

    else:
        st.subheader("❌ Position schließen & ins Journal übertragen")
        
        sell_depot = st.selectbox("Aus welchem Depot wird verkauft?", list(depot_tables.keys()), key="sell_depot_select")
        sell_tbl = depot_tables[sell_depot]
        
        try:
            res_open = supabase.table(sell_tbl).select("*").execute()
            open_pos = res_open.data
            
            if open_pos:
                pos_options = {f"{p['ticker']} ({p['anzahl']} Anteile @ {p['buy_price']}€) [ID: {p['id']}]": p for p in open_pos}
                
                selected_pos_label = st.selectbox("Wähle die zu schließende Position:", list(pos_options.keys()))
                chosen_pos = pos_options[selected_pos_label]
                
                with st.form("sell_form"):
                    col_s1, col_s2 = st.columns(2)
                    with col_s1:
                        s_price = st.number_input("Ausstiegspreis pro Einheit (€)", min_value=0.01, value=float(chosen_pos['buy_price']), format="%.2f")
                        s_shares_to_sell = st.number_input("Anzahl Anteile", min_value=0.0001, max_value=float(chosen_pos['anzahl']), value=float(chosen_pos['anzahl']), format="%.4f")
                    with col_s2:
                        s_date = st.date_input("Ausstiegsdatum", value="today")
                        s_time = st.time_input("Ausstiegszeit", value=datetime.now().time())
                    
                    s_note = st.text_area("Notiz / Lernkurve (Warum wurde der Trade geschlossen?):", placeholder="Z.B.: 'Makro-Umfeld hat sich gedreht, Take-Profit erreicht.'")
                    
                    submitted_sell = st.form_submit_button("Trade schließen & ins Journal schreiben")
                    
                    if submitted_sell:
                        s_timestamp = datetime.combine(s_date, s_time).isoformat()
                        buy_p = float(chosen_pos['buy_price'])
                        exit_gesamtwert = s_shares_to_sell * s_price
                        performance_pct = ((s_price - buy_p) / buy_p) * 100 if buy_p > 0 else 0
                        
                        # Ins Journal schreiben
                        supabase.table("trade_journal").insert({
                            "ticker": chosen_pos['ticker'],
                            "einstieg_datum_zeit": chosen_pos['datum_einstieg'],
                            "ausstieg_datum_zeit": s_timestamp,
                            "anzahl": s_shares_to_sell,
                            "gesamtwert": exit_gesamtwert,
                            "signaltype": sell_depot,
                            "performance": performance_pct,
                            "notiz": s_note
                        }).execute()
                        
                        # Aus aktivem Depot entfernen
                        supabase.table(sell_tbl).delete().eq("id", chosen_pos['id']).execute()
                        
                        st.success(f"Trade für {chosen_pos['ticker']} erfolgreich geschlossen und im Journal verankert!")
                        st.rerun()
            else:
                st.info(f"Keine offenen Positionen in `{sell_depot}` vorhanden.")
                
        except Exception as e:
            st.error(f"Fehler beim Laden der Positionen: {e}")