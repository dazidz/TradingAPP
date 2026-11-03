from datetime import datetime
from supabase import create_client
import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(
    layout="wide",
    page_title="VisionDZ - Depot & Journal",
    page_icon="📈",
)

if not st.session_state.get("password_correct", False):
  st.warning("Bitte melde dich zuerst auf der Hauptseite an.")
  st.stop()

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

st.title("📈 VisionDZ - Depot & Trading Journal")
st.markdown(
    "Live-Überwachung der Portfolios und lückenloses Journal geschlossener"
    " Trades nach Dalio-Prinzipien."
)

tab_depot, tab_journal, tab_new_trade = st.tabs([
    "💼 Offene Depots",
    "📖 Trade Journal (Geschlossen)",
    "➕ Position eröffnen / schließen",
])

depot_tables = {
    "Invest Depot": "invest_depot",
    "Swing Depot": "swing_depot",
    "Risiko Depot": "risk_depot",
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
      key="depot_radio",
  )

  target_table = depot_tables[selected_depot_ui]

  try:
    try:
      wl_res = (
          supabase.table("watchlist").select("ticker, company_name").execute()
      )
      ticker_to_name = (
          {
              item["ticker"]: item.get("company_name", item["ticker"])
              for item in wl_res.data
          }
          if wl_res.data
          else {}
      )
    except Exception:
      ticker_to_name = {}

    response = supabase.table(target_table).select("*").execute()
    positions = response.data

    if positions:
      df_pos = pd.DataFrame(positions)

      tickers = df_pos["ticker"].unique().tolist()
      live_prices = {}
      if tickers:
        df_hist = yf.download(
            tickers, period="1d", progress=False, auto_adjust=True
        )
        for t in tickers:
          try:
            if len(tickers) == 1:
              live_prices[t] = float(df_hist["Close"].iloc[-1])
            else:
              live_prices[t] = float(df_hist["Close"][t].iloc[-1])
          except Exception:
            live_prices[t] = 0.0

      portfolio_data = []
      total_value = 0
      total_invested = 0

      for _, row in df_pos.iterrows():
        ticker = row["ticker"]
        # Fallback auf Watchlist/yfinance, falls das Feld in Supabase mal leer sein sollte
        db_unternehmen = row.get("unternehmen", None)
        if not db_unternehmen or pd.isna(db_unternehmen):
          company_name = ticker_to_name.get(ticker, ticker)
        else:
          company_name = db_unternehmen

        shares = float(row["anzahl"])
        buy_price = float(row["buy_price"])
        curr_price = live_prices.get(ticker, buy_price)

        inv_val = shares * buy_price
        curr_val = shares * curr_price
        pnl_pct = (
            ((curr_price - buy_price) / buy_price) * 100
            if buy_price > 0
            else 0
        )

        total_invested += inv_val
        total_value += curr_val

        try:
          supabase.table(target_table).update({
              "live_kurs": curr_price,
              "gesamtwert": curr_val,
              "performance": pnl_pct,
          }).eq("id", row["id"]).execute()
        except Exception:
          pass

        portfolio_data.append({
            "ID": row["id"],
            "Unternehmen": company_name,
            "Ticker": ticker,
            "Datum Einstieg": row.get("datum_einstieg", "N/A"),
            "Anzahl": shares,
            "Kaufpreis (€)": buy_price,
            "Live-Kurs (€)": curr_price,
            "Gesamtwert (€)": curr_val,
            "Performance (%)": pnl_pct,
        })

      total_pnl = total_value - total_invested
      total_pnl_pct = (
          (total_pnl / total_invested) * 100 if total_invested > 0 else 0
      )

      m1, m2, m3 = st.columns(3)
      m1.metric("Gesamtwert Depot", f"{total_value:,.2f} €")
      m2.metric("Gesamtes Invest", f"{total_invested:,.2f} €")
      m3.metric(
          "Gesamt-Performance", f"{total_pnl:+.2f} €", f"{total_pnl_pct:+.2f}%"
      )

      st.divider()

      df_display = pd.DataFrame(portfolio_data)
      st.dataframe(
          df_display.drop(columns=["ID"]),
          column_config={
              "Kaufpreis (€)": st.column_config.NumberColumn(format="%.2f €"),
              "Live-Kurs (€)": st.column_config.NumberColumn(format="%.2f €"),
              "Gesamtwert (€)": st.column_config.NumberColumn(format="%.2f €"),
              "Performance (%)": st.column_config.NumberColumn(format="%.2f%%"),
              "Anzahl": st.column_config.NumberColumn(format="%.4f"),
          },
          use_container_width=True,
      )

    else:
      st.info(f"Keine offenen Positionen im `{selected_depot_ui}` vorhanden.")

  except Exception as e:
    st.error(f"Fehler beim Laden von `{target_table}`: {e}")

# ==========================================
# TAB 2: DAS TRADING JOURNAL (GESCHLOSSENE TRADES)
# ==========================================
with tab_journal:
  try:
    res_journal = (
        supabase.table("trade_journal")
        .select("*")
        .order("ausstieg_datum_zeit", desc=True)
        .execute()
    )
    journal_data = res_journal.data

    if journal_data:
      df_j = pd.DataFrame(journal_data)

      # Watchlist für Fallback-Firmennamen im Journal laden
      try:
        wl_res = (
            supabase.table("watchlist").select("ticker, company_name").execute()
        )
        j_ticker_to_name = (
            {
                item["ticker"]: item.get("company_name", item["ticker"])
                for item in wl_res.data
            }
            if wl_res.data
            else {}
        )
      except Exception:
        j_ticker_to_name = {}

      # Unternehmen aus der DB holen, falls leer per Map ergänzen
      def resolve_journal_name(row):
        val = row.get("unternehmen", None)
        if val and pd.notna(val):
          return val
        t = row["ticker"]
        return j_ticker_to_name.get(t, t)

      df_j["Unternehmen"] = df_j.apply(resolve_journal_name, axis=1)

      # Filter für Mandate im Journal
      filter_options = ["Alle Mandate"] + list(depot_tables.keys())
      selected_journal_filter = st.selectbox(
          "Journal filtern nach Mandat:", filter_options
      )

      if selected_journal_filter != "Alle Mandate":
        df_j_filtered = df_j[df_j["signaltype"] == selected_journal_filter]
      else:
        df_j_filtered = df_j

      total_trades = len(df_j_filtered)

      if (
          "g_v" in df_j_filtered.columns
          and df_j_filtered["g_v"].notna().any()
      ):
        winning_trades = len(df_j_filtered[df_j_filtered["g_v"] > 0])
        losing_trades = len(df_j_filtered[df_j_filtered["g_v"] < 0])
        win_rate = (
            (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        )
        total_g_v = df_j_filtered["g_v"].sum()
        avg_g_v = df_j_filtered["g_v"].mean()
      else:
        winning_trades, losing_trades, win_rate, total_g_v, avg_g_v = (
            0,
            0,
            0,
            0,
            0,
        )

      if (
          "performance" in df_j_filtered.columns
          and df_j_filtered["performance"].notna().any()
      ):
        avg_performance = df_j_filtered["performance"].mean()
      else:
        avg_performance = 0.0

      col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
      col_kpi1.metric(
          "Win-Rate",
          f"{win_rate:.1f}%",
          f"Gewinner: {winning_trades} / {total_trades}",
      )
      col_kpi2.metric("Ø Performance", f"{avg_performance:+.2f}%")
      col_kpi3.metric("Gesamt G/V", f"{total_g_v:+,.2f} €")
      col_kpi4.metric("Ø G/V pro Trade", f"{avg_g_v:+,.2f} €")

      st.divider()

      display_cols = [
          c
          for c in [
              "Unternehmen",
              "ticker",
              "signaltype",
              "einstieg_datum_zeit",
              "ausstieg_datum_zeit",
              "anzahl",
              "einstiegskurs",
              "ausstiegskurs",
              "gesamtwert",
              "performance",
              "g_v",
              "notiz",
          ]
          if c in df_j_filtered.columns
      ]

      st.dataframe(
          df_j_filtered[display_cols],
          column_config={
              "Unternehmen": "Unternehmen",
              "ticker": "Ticker",
              "signaltype": "Mandat",
              "einstieg_datum_zeit": "Einstieg",
              "ausstieg_datum_zeit": "Ausstieg",
              "anzahl": st.column_config.NumberColumn("Anzahl", format="%.4f"),
              "einstiegskurs": st.column_config.NumberColumn(
                  "Einstiegskurs", format="%.2f €"
              ),
              "ausstiegskurs": st.column_config.NumberColumn(
                  "Ausstiegskurs", format="%.2f €"
              ),
              "gesamtwert": st.column_config.NumberColumn(
                  "Gesamtwert", format="%.2f €"
              ),
              "performance": st.column_config.NumberColumn(
                  "Performance", format="%.2f%%"
              ),
              "g_v": st.column_config.NumberColumn(
                  "Gewinn / Verlust (G/V)", format="%.2f €"
              ),
              "notiz": "Notiz / Lernkurve",
          },
          use_container_width=True,
      )
    else:
      st.info("Noch keine geschlossenen Trades im Journal erfasst.")
  except Exception as e:
    st.error(f"Fehler beim Laden des Journals: {e}")

# ==========================================
# TAB 3: POSITION ERÖFFNEN ODER SCHLIESSEN
# ==========================================
with tab_new_trade:
  action_mode = st.radio(
      "Aktion wählen:",
      [
          "Neue Position kaufen (BUY)",
          "Bestehende Position schließen (SELL)",
      ],
      horizontal=True,
  )
  st.divider()

  if action_mode == "Neue Position kaufen (BUY)":
    st.subheader("➕ Neue Position im Depot eröffnen")

    try:
      wl_res = (
          supabase.table("watchlist").select("ticker, company_name").execute()
      )
      watchlist_items = wl_res.data if wl_res.data else []
    except Exception:
      watchlist_items = []

    # Map von Anzeigetext zu Ticker & Unternehmensnamen
    ticker_options = {}
    for item in watchlist_items:
      c_name = item.get("company_name", "N/A")
      t_sym = item["ticker"]
      ticker_options[f"{c_name} ({t_sym})"] = {
          "ticker": t_sym,
          "company_name": c_name,
      }

    with st.form("buy_form"):
      col_b1, col_b2 = st.columns(2)

      with col_b1:
        if ticker_options:
          selected_display = st.selectbox(
              "Unternehmen aus Watchlist wählen",
              options=list(ticker_options.keys()),
          )
          b_ticker = ticker_options[selected_display]["ticker"]
          b_company_name = ticker_options[selected_display]["company_name"]
        else:
          b_ticker = st.text_input(
              "Ticker-Symbol (z.B. AAPL, GC=F)"
          ).upper()
          b_company_name = b_ticker

        b_depot = st.selectbox(
            "Ziel-Depot", list(depot_tables.keys()), key="buy_depot"
        )

      with col_b2:
        b_shares = st.number_input(
            "Anzahl", min_value=0.0001, value=1.0, format="%.4f", key="buy_shares"
        )
        b_price = st.number_input(
            "Kaufpreis pro Einheit (€)",
            min_value=0.01,
            value=100.0,
            format="%.2f",
            key="buy_price",
        )

      col_d1, col_d2 = st.columns(2)
      with col_d1:
        b_date = st.date_input("Einstiegsdatum", value="today", key="buy_date")
      with col_d2:
        b_time = st.time_input(
            "Einstiegszeit", value=datetime.now().time(), key="buy_time"
        )

      submitted_buy = st.form_submit_button("Position in Depot aufnehmen")

      if submitted_buy:
        if b_ticker:
          try:
            b_timestamp = datetime.combine(b_date, b_time).isoformat()
            target_tbl = depot_tables[b_depot]
            initial_val = b_shares * b_price

            # Firmenname direkt über yfinance absichern, falls nicht aus Watchlist
            if not b_company_name or b_company_name == b_ticker:
              try:
                info = yf.Ticker(b_ticker).info
                b_company_name = info.get(
                    "longName", info.get("shortName", b_ticker)
                )
              except Exception:
                b_company_name = b_ticker

            # Schreiben in Supabase inklusive des Unternehmensnamens
            supabase.table(target_tbl).insert({
                "ticker": b_ticker,
                "unternehmen": b_company_name,
                "datum_einstieg": b_timestamp,
                "anzahl": b_shares,
                "buy_price": b_price,
                "live_kurs": b_price,
                "gesamtwert": initial_val,
                "performance": 0.0,
            }).execute()

            st.success(
                f"Position {b_company_name} ({b_ticker}) erfolgreich in"
                f" `{b_depot}` eröffnet!"
            )
            st.rerun()
          except Exception as e:
            st.error(f"Fehler beim Speichern: {e}")
        else:
            st.warning("Bitte Ticker eingeben.")

  else:
    st.subheader(
        "❌ Position schließen / Teilverkauf & ins Journal übertragen"
    )

    sell_depot = st.selectbox(
        "Aus welchem Depot wird verkauft?",
        list(depot_tables.keys()),
        key="sell_depot_select",
    )
    sell_tbl = depot_tables[sell_depot]

    try:
      res_open = supabase.table(sell_tbl).select("*").execute()
      open_pos = res_open.data

      if open_pos:
        pos_options = {}
        for p in open_pos:
          comp = p.get("unternehmen", p["ticker"])
          label = (
              f"{comp} ({p['ticker']}) - {p['anzahl']} Stk. @"
              f" {p['buy_price']}€ [ID: {p['id']}]"
          )
          pos_options[label] = p

        selected_pos_label = st.selectbox(
            "Wähle die Position:", list(pos_options.keys())
        )
        chosen_pos = pos_options[selected_pos_label]

        with st.form("sell_form"):
          col_s1, col_s2 = st.columns(2)
          with col_s1:
            s_price = st.number_input(
                "Ausstiegspreis pro Einheit (€)",
                min_value=0.01,
                value=float(chosen_pos["buy_price"]),
                format="%.2f",
            )
            s_shares_to_sell = st.number_input(
                "Anzahl Anteile zum Verkaufen",
                min_value=0.0001,
                max_value=float(chosen_pos["anzahl"]),
                value=float(chosen_pos["anzahl"]),
                format="%.4f",
            )
          with col_s2:
            s_date = st.date_input("Ausstiegsdatum", value="today")
            s_time = st.time_input(
                "Ausstiegszeit", value=datetime.now().time()
            )

          s_note = st.text_area(
              "Notiz / Lernkurve (Warum wurde verkauft?):",
              placeholder=(
                  "Z.B.: 'Teilgewinnmitnahme nach starkem Anstieg.'"
              ),
          )

          submitted_sell = st.form_submit_button(
              "Verkauf ausführen & ins Journal schreiben"
          )

          if submitted_sell:
            s_timestamp = datetime.combine(s_date, s_time).isoformat()
            buy_p = float(chosen_pos["buy_price"])
            total_shares_owned = float(chosen_pos["anzahl"])

            exit_gesamtwert = s_shares_to_sell * s_price
            performance_pct = (
                ((s_price - buy_p) / buy_p) * 100 if buy_p > 0 else 0
            )
            trade_g_v = (s_price - buy_p) * s_shares_to_sell

            # Unternehmensnamen für das Journal übernehmen
            position_unternehmen = chosen_pos.get("unternehmen", chosen_pos["ticker"])

            supabase.table("trade_journal").insert({
                "ticker": chosen_pos["ticker"],
                "unternehmen": position_unternehmen,
                "einstieg_datum_zeit": chosen_pos["datum_einstieg"],
                "ausstieg_datum_zeit": s_timestamp,
                "anzahl": s_shares_to_sell,
                "einstiegskurs": buy_p,
                "ausstiegskurs": s_price,
                "gesamtwert": exit_gesamtwert,
                "signaltype": sell_depot,
                "performance": performance_pct,
                "g_v": round(trade_g_v, 2),
                "notiz": s_note,
            }).execute()

            if s_shares_to_sell >= total_shares_owned:
              supabase.table(sell_tbl).delete().eq(
                  "id", chosen_pos["id"]
              ).execute()
              st.success(
                  f"Position für {position_unternehmen} ({chosen_pos['ticker']}) komplett geschlossen und"
                  " ins Journal übertragen!"
              )
            else:
              remaining_shares = total_shares_owned - s_shares_to_sell
              remaining_gesamtwert = remaining_shares * buy_p

              supabase.table(sell_tbl).update({
                  "anzahl": remaining_shares,
                  "gesamtwert": remaining_gesamtwert,
              }).eq("id", chosen_pos["id"]).execute()
              st.success(
                  f"Teilverkauf von {s_shares_to_sell} Anteilen"
                  f" {position_unternehmen} verbucht. Rest im Depot:"
                  f" {remaining_shares} Anteile."
              )

            st.rerun()
      else:
        st.info(f"Keine offenen Positionen in `{sell_depot}` vorhanden.")

    except Exception as e:
      st.error(f"Fehler beim Verarbeiten des Verkaufs: {e}")