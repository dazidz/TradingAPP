import json
import altair as alt
import pandas as pd
import streamlit as st
from supabase import create_client
import yfinance as yf

# Passwort-Schutz
if "password_correct" not in st.session_state or not st.session_state.password_correct:
  st.error("Bitte zuerst auf der Startseite anmelden!")
  st.stop()

st.title("📊 Ticker-Screener")

# --- SEITENBAR & CACHE CONTROL ---
with st.sidebar:
  st.markdown("### ⚙️ Steuerung")
  if st.button("🔄 Cache leeren & Aktualisieren", use_container_width=True):
    st.cache_data.clear()
    st.success("Cache erfolgreich geleert!")
    st.rerun()

# Verbindung zu Supabase
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)


# Caching für Daten & Exchange-Informationen
@st.cache_data(ttl=3600)
def get_stock_meta(tickers):
  prices = {}
  exchanges = {}
  if not tickers:
    return prices, exchanges
  for ticker in tickers:
    try:
      t = yf.Ticker(ticker)
      hist = t.history(period="1d")
      if not hist.empty:
        prices[ticker] = float(hist["Close"].iloc[-1])

      info = t.info
      exchanges[ticker] = info.get("exchange", "N/A")
    except Exception:
      continue
  return prices, exchanges


@st.cache_data(ttl=3600)
def get_ema_stats_bulk(tickers):
  stats = {}
  if not tickers:
    return stats
  try:
    data = yf.download(tickers, period="1mo", interval="1d", progress=False)
    if "Close" in data:
      data = data["Close"]
    for ticker in tickers:
      try:
        series = (
            data[ticker].dropna()
            if isinstance(data, pd.DataFrame)
            else data.dropna()
        )
        if len(series) >= 20:
          ema20 = series.ewm(span=20, adjust=False).mean().iloc[-1]
          stats[ticker] = float(((series.iloc[-1] - ema20) / ema20) * 100)
      except Exception:
        stats[ticker] = None
  except Exception:
    pass
  return stats


# --- SCREENER LOGIK ---
try:
  # 1. Aktive Signale laden
  response = supabase.table("signals").select("*").execute()
  df = pd.DataFrame(response.data)

  # 2. Favoriten aus der separaten Tabelle laden
  fav_response = supabase.table("favorites").select("ticker").execute()
  fav_tickers = (
      [row["ticker"] for row in fav_response.data] if fav_response.data else []
  )

  if not df.empty:
    df = df.drop_duplicates(
        subset=["ticker", "signal_type"], keep="last"
    ).reset_index(drop=True)

    if "meta_data" in df.columns:

      def parse_meta(x):
        if isinstance(x, dict):
          return x
        if isinstance(x, str) and x.startswith("{"):
          try:
            fixed_str = (
                x.replace("'", '"')
                .replace("true", "true")
                .replace("false", "false")
            )
            return json.loads(fixed_str)
          except Exception:
            return {}
        return {}

      df["meta_data"] = df["meta_data"].apply(parse_meta)
      meta_df = pd.json_normalize(df["meta_data"])
      df = pd.concat([df.drop(columns=["meta_data"]), meta_df], axis=1)

    for col in [
        "gettex_ticker",
        "entry_price",
        "sector",
        "company_name",
        "candle_time",
        "ticker",
        "signal_type",
    ]:
      if col not in df.columns:
        df[col] = ""

    # Status direkt über die Favoriten-Tabelle setzen
    df["is_favorite"] = df["ticker"].isin(fav_tickers)

    df["Chart"] = df["gettex_ticker"].apply(
        lambda x: f"https://www.tradingview.com/chart/?symbol={x}" if x else ""
    )

    unique_tickers = [t for t in df["ticker"].unique().tolist() if t]
    prices, exchanges = get_stock_meta(unique_tickers)
    ema_stats = get_ema_stats_bulk(unique_tickers)

    df["current_price"] = df["ticker"].map(prices)
    df["exchange"] = df["ticker"].map(exchanges)

    df["entry_price_num"] = pd.to_numeric(df["entry_price"], errors="coerce")
    df["Performance (%)"] = (
        (df["current_price"] - df["entry_price_num"]) / df["entry_price_num"]
    ) * 100
    df["EMA20_Dist_%"] = df["ticker"].map(ema_stats)

    # Globale Sektor-Anteile für das Diagramm
    total_count_global = len(df)
    sector_counts_global = df.groupby("sector").size()
    sector_share_global = (sector_counts_global / total_count_global) * 100

    # Tabs für die einzelnen Kategorien
    (
        tab_favs,
        tab_ema20_elite,
        tab_ema20,
        tab_unter_elite,
        tab_unter_ema20,
        tab_dip,
    ) = st.tabs([
        "⭐ Favoriten",
        "🟣 EMA20+ELITE",
        "🟢 EMA20",
        "🟡 unter EMA20+ELITE",
        "🔴 unter EMA20",
        "📉 Dip-Scanner",
    ])

    def show_table(df_subset, category_type="default"):
      d = df_subset.copy()
      if d.empty:
        st.info("Keine Daten für diese Filtereinstellung vorhanden.")
        return

      d["Action"] = False

      # Präfix-Logik je nach Kategorie/Zustand
      def get_company_prefix(row):
        sig = str(row.get("signal_type", "")).strip().lower()
        dist = row.get("EMA20_Dist_%", 0)
        if pd.isna(dist):
          dist = 0

        if category_type == "favorites":
          return f"⭐ {row.get('company_name', '')}"
        elif category_type == "ema20_elite":
          return f"🟣 {row.get('company_name', '')}"
        elif category_type == "ema20":
          return f"🟢 {row.get('company_name', '')}"
        elif category_type == "unter_elite":
          return f"🟡 {row.get('company_name', '')}"
        elif category_type == "unter_ema20":
          return f"🔴 {row.get('company_name', '')}"
        else:
          # Fallback (z.B. Gesamtansicht, falls gewünscht)
          if "elite" in sig:
            return (
                f"🟣 {row.get('company_name', '')}"
                if dist >= 0
                else f"🟡 {row.get('company_name', '')}"
            )
          else:
            return (
                f"🟢 {row.get('company_name', '')}"
                if dist >= 0
                else f"🔴 {row.get('company_name', '')}"
            )

      d["company_name_formatted"] = d.apply(get_company_prefix, axis=1)

      cols = [
          "Action",
          "company_name_formatted",
          "Chart",
          "Performance (%)",
          "candle_time",
          "sector",
          "signal_type",
          "gettex_ticker",
      ]

      conf = {
          "company_name_formatted": st.column_config.TextColumn(
              "Firma", disabled=True
          ),
          "Chart": st.column_config.LinkColumn("Link", display_text="📈 Öffnen"),
          "Performance (%)": st.column_config.NumberColumn(
              "Performance", format="%.2f%%"
          ),
          "candle_time": st.column_config.TextColumn("Candle Time"),
          "sector": st.column_config.TextColumn("Sektor", disabled=True),
          "signal_type": st.column_config.TextColumn(
              "Signal Type", disabled=True
          ),
          "gettex_ticker": st.column_config.TextColumn(
              "Gettex Ticker", disabled=True
          ),
          "Action": st.column_config.CheckboxColumn(
              "Entfernen" if category_type == "favorites" else "Favorit",
              default=False,
          ),
      }

      existing_cols = [c for c in cols if c in d.columns]

      # --- DIAGRAMM (Kombinierter Score) ---
      if "sector" in d.columns and "Performance (%)" in d.columns:
        chart_data = d[
            (d["Performance (%)"] < 3.0) & (d["Performance (%)"].notnull())
        ]
        if not chart_data.empty and "sector" in chart_data.columns:
          total_subset_count = len(chart_data)
          sector_counts_subset = chart_data.groupby("sector").size()

          sector_share_subset = (
              sector_counts_subset / total_subset_count
          ) * 100

          sector_df = pd.DataFrame({
              "Anteil_Signale": sector_share_subset,
              "Anteil_Watchlist": sector_share_global,
              "Treffer": sector_counts_subset,
              "Gesamt_WL": sector_counts_global,
          }).dropna()

          sector_df["Score"] = sector_df["Treffer"] * (
              (sector_df["Anteil_Signale"] + 1)
              / (sector_df["Anteil_Watchlist"] + 1)
          )

          sector_df = (
              sector_df.reset_index()
              .sort_values(by="Score", ascending=False)
              .head(10)
          )

          if not sector_df.empty:
            c = (
                alt.Chart(sector_df)
                .mark_bar(color="#3b82f6")
                .encode(
                    x=alt.X(
                        "Score:Q",
                        title="Sektor-Score (Treffer & Gewichtung kombiniert)",
                        axis=alt.Axis(format=".1f"),
                    ),
                    y=alt.Y("sector:N", sort="-x", title="Sektor"),
                    tooltip=[
                        "sector",
                        alt.Tooltip("Score:Q", format=".2f", title="Score"),
                        alt.Tooltip(
                            "Anteil_Signale:Q",
                            format=".1f",
                            title="Anteil Signale (%)",
                        ),
                        alt.Tooltip(
                            "Anteil_Watchlist:Q",
                            format=".1f",
                            title="Anteil Watchlist (%)",
                        ),
                        "Treffer",
                        "Gesamt_WL",
                    ],
                )
                .properties(height=250)
            )
            st.altair_chart(c, use_container_width=True)

      if (
          "Performance (%)" in d.columns
          and not d["Performance (%)"].dropna().empty
      ):
        avg_perf = d["Performance (%)"].mean()
        st.metric("Ø Performance der Liste", f"{avg_perf:.2f}%")

      edited = st.data_editor(
          d[existing_cols],
          column_config=conf,
          hide_index=True,
          use_container_width=True,
      )

      changed_rows = edited[edited["Action"] == True]
      if not changed_rows.empty:
        for _, row in changed_rows.iterrows():
          orig_row_idx = edited[edited["Action"] == True].index[0]
          t_symbol = d.loc[orig_row_idx, "ticker"]

          if category_type == "favorites":
            supabase.table("favorites").delete().eq(
                "ticker", t_symbol
            ).execute()
          else:
            supabase.table("favorites").upsert(
                {"ticker": t_symbol}, on_conflict="ticker"
            ).execute()
        st.rerun()

    # Hilfsfunktion zur Prüfung auf Elite im Signaltyp
    def is_elite(sig):
      return "elite" in str(sig).lower()

    # Tab 1: Favoriten
    with tab_favs:
      show_table(df[df["is_favorite"] == True], category_type="favorites")

    # Tab 2: EMA20 + ELITE (dist >= 0 und elite)
    with tab_ema20_elite:
      show_table(
          df[
              (df.get("status") == "signal")
              & (df["EMA20_Dist_%"].fillna(-1) >= 0)
              & (df["signal_type"].apply(is_elite))
          ],
          category_type="ema20_elite",
      )

    # Tab 3: EMA20 (dist >= 0 und kein elite)
    with tab_ema20:
      show_table(
          df[
              (df.get("status") == "signal")
              & (df["EMA20_Dist_%"].fillna(-1) >= 0)
              & (~df["signal_type"].apply(is_elite))
          ],
          category_type="ema20",
      )

    # Tab 4: unter EMA20 + ELITE (dist < 0 und elite)
    with tab_unter_elite:
      show_table(
          df[
              (df.get("status") == "signal")
              & (df["EMA20_Dist_%"].fillna(0) < 0)
              & (df["signal_type"].apply(is_elite))
          ],
          category_type="unter_elite",
      )

    # Tab 5: unter EMA20 (dist < 0 und kein elite)
    with tab_unter_ema20:
      show_table(
          df[
              (df.get("status") == "signal")
              & (df["EMA20_Dist_%"].fillna(0) < 0)
              & (~df["signal_type"].apply(is_elite))
          ],
          category_type="unter_ema20",
      )

    # --- TAB: DIP-SCANNER ---
    with tab_dip:
      st.subheader(
          "📉 Dip-Scanner: Aktien mit $\\ge$ 20% Korrektur vom Allzeithoch"
      )
      st.markdown(
          "Solide Werte aus deiner Watchlist, die sich in einer tieferen"
          " Konsolidierung befinden."
      )

      try:
        dip_response = (
            supabase.table("watchlist")
            .select(
                "ticker, company_name, sector, gettex_ticker, current_price,"
                " ath, distance_from_ath"
            )
            .lte("distance_from_ath", -20.0)
            .order("distance_from_ath", desc=False)
            .execute()
        )

        dip_data = dip_response.data

        if dip_data:
          df_dip = pd.DataFrame(dip_data)
          df_dip["Chart"] = df_dip["gettex_ticker"].apply(
              lambda x: (
                  f"https://www.tradingview.com/chart/?symbol={x}" if x else ""
              )
          )

          dip_cols = [
              "company_name",
              "Chart",
              "sector",
              "current_price",
              "ath",
              "distance_from_ath",
              "gettex_ticker",
          ]
          existing_dip_cols = [c for c in dip_cols if c in df_dip.columns]

          dip_conf = {
              "company_name": st.column_config.TextColumn(
                  "Firma", disabled=True
              ),
              "Chart": st.column_config.LinkColumn(
                  "Link", display_text="📈 Öffnen"
              ),
              "sector": st.column_config.TextColumn("Sektor", disabled=True),
              "current_price": st.column_config.NumberColumn(
                  "Aktueller Kurs", format="€%.2f"
              ),
              "ath": st.column_config.NumberColumn(
                  "Allzeithoch (ATH)", format="€%.2f"
              ),
              "distance_from_ath": st.column_config.NumberColumn(
                  "Abstand vom ATH", format="%.2f%%"
              ),
              "gettex_ticker": st.column_config.TextColumn(
                  "Gettex Ticker", disabled=True
              ),
          }

          st.dataframe(
              df_dip[existing_dip_cols],
              column_config=dip_conf,
              hide_index=True,
              use_container_width=True,
          )
        else:
          st.info(
              "Aktuell befinden sich keine Aktien aus der Watchlist im Bereich"
              " von -20% oder tiefer vom Allzeithoch."
          )
      except Exception as e:
        st.error(f"Fehler beim Laden der Dip-Daten: {e}")

  else:
    st.info("Keine Daten in der Supabase-Datenbank vorhanden.")

except Exception as e:
  st.error(f"Fehler: {e}")