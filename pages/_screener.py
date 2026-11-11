import json
import altair as alt
import pandas as pd
import streamlit as st
from supabase import create_client
import yfinance as yf

# Irma (Sektor-Assistenz) importieren
from employees_test.irma import IrmaSectorAssistant

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

# Irma initialisieren
irma = IrmaSectorAssistant(supabase)


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


def is_elite(sig):
    return "elite" in str(sig).lower()


# --- DATEN LADEN & VORBEREITEN (Basis für Diagramm & Tabellen) ---
try:
    response = supabase.table("signals").select("*").execute()
    df = pd.DataFrame(response.data)

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
        
        # Exakte Performance seit Candle Time (Entry Price)
        df["Performance (%)"] = (
            (df["current_price"] - df["entry_price_num"]) / df["entry_price_num"]
        ) * 100
        df["EMA20_Dist_%"] = df["ticker"].map(ema_stats)

        # --- IRMA SEKTOR FILTER & MODUS-AUSWAHL ---
        col_filter1, col_filter2, _ = st.columns([2, 2, 2])
        with col_filter1:
            signal_choice = st.selectbox(
                "🎯 Filter für Irma Sektor-Analyse:",
                options=["ALL", "ELITE", "ELITE_EMA", "KAUF", "KAUF_EMA"],
                format_func=lambda x: {
                    "ALL": "Alle Signale",
                    "ELITE": "Elite Signale",
                    "ELITE_EMA": "Elite + Über EMA20",
                    "KAUF": "Kauf Signale",
                    "KAUF_EMA": "Kauf + Über EMA20",
                }[x],
            )

        with col_filter2:
            sector_view_mode = st.selectbox(
                "🏛️ Sektor-Ansicht:",
                options=[
                    "🎯 Chancen-Score (Seit Signal)",
                    "📊 Prozentuale Signal-Quote (Alt)",
                ],
            )

        # Passendes Subset für den gewählten Filter ziehen (damit nur relevante Signale gewichtet werden)
        df_filtered = df.copy()
        if signal_choice == "ELITE":
            df_filtered = df_filtered[df_filtered["signal_type"].apply(is_elite)]
        elif signal_choice == "ELITE_EMA":
            df_filtered = df_filtered[
                df_filtered["signal_type"].apply(is_elite)
                & (df_filtered["EMA20_Dist_%"].notna())
                & (df_filtered["EMA20_Dist_%"] >= 0)
            ]
        elif signal_choice == "KAUF":
            df_filtered = df_filtered[~df_filtered["signal_type"].apply(is_elite)]
        elif signal_choice == "KAUF_EMA":
            df_filtered = df_filtered[
                (~df_filtered["signal_type"].apply(is_elite))
                & (df_filtered["EMA20_Dist_%"].notna())
                & (df_filtered["EMA20_Dist_%"] >= 0)
            ]

        # Basis-Quoten von Irma holen
        sector_base = irma.get_top_sector_quotas(signal_filter=signal_choice)

        if "Chancen-Score" in sector_view_mode:
            st.markdown(
                f"### 🎯 Irma: Top 10 Sektoren nach Chancen-Score ({signal_choice})"
            )

            if not sector_base.empty and not df_filtered.empty:
                # Durchschnittliche Performance seit Candle Time pro Sektor (ohne NaNs!)
                valid_perf = df_filtered.dropna(subset=["Performance (%)", "sector"])
                valid_perf = valid_perf[valid_perf["sector"] != ""]
                
                perf_agg = (
                    valid_perf.groupby("sector")["Performance (%)"]
                    .mean()
                    .reset_index()
                    .rename(columns={"Performance (%)": "avg_perf_since_signal"})
                )

                # Striktes Inner Merge: Sektoren ohne valide Performance fliegen raus
                df_valid = pd.merge(sector_base, perf_agg, on="sector", how="inner")

                valid_sectors = set(df_valid["sector"])
                ignored_sectors = [
                    s for s in sector_base["sector"] if s not in valid_sectors
                ]

                if ignored_sectors:
                    st.warning(
                        f"⚠️ Ignorierte Sektoren (keine validen Kurs-/Entry-Daten): **{', '.join(ignored_sectors)}**"
                    )

                def calc_score(row):
                    perf = row["avg_perf_since_signal"]
                    quota = row.get("signal_quota_percent", 0)

                    # Erschöpfungs-Malus basierend auf Lauf seit Candle Time
                    if perf > 15.0:
                        exhaustion_penalty = 0.2  # Schon extrem gelaufen (>15%)
                    elif perf > 8.0:
                        exhaustion_penalty = 0.5  # Gut angelaufen (8-15%)
                    else:
                        exhaustion_penalty = 1.0  # Frisch (<8%)

                    score = quota * exhaustion_penalty
                    # Leichter Bonus, wenn Signale noch leicht im Minus / am Einstieg liegen
                    if -10.0 <= perf < 0:
                        score += abs(perf) * 1.2
                    return score

                df_valid["opportunity_score"] = df_valid.apply(calc_score, axis=1)
                df_chart = df_valid.sort_values(
                    by="opportunity_score", ascending=False
                ).head(10)

                if not df_chart.empty:
                    chart = (
                        alt.Chart(df_chart)
                        .mark_bar(color="#3b82f6")
                        .encode(
                            x=alt.X(
                                "opportunity_score:Q",
                                title="Chancen-Score (Quote × Frische)",
                                axis=alt.Axis(format=".1f"),
                            ),
                            y=alt.Y("sector:N", sort="-x", title="Sektor"),
                            tooltip=[
                                "sector",
                                alt.Tooltip(
                                    "opportunity_score:Q", format=".1f", title="Score"
                                ),
                                alt.Tooltip(
                                    "avg_perf_since_signal:Q",
                                    format=".2f",
                                    title="Ø Perf seit Signal (%)",
                                ),
                                alt.Tooltip(
                                    "signal_quota_percent:Q",
                                    format=".1f",
                                    title="Signal-Quote (%)",
                                ),
                                alt.Tooltip(
                                    "signal_tickers:Q", title="Ticker mit Signal"
                                ),
                            ],
                        )
                        .properties(height=420)
                    )
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.info("Keine validen Sektordaten für den Chancen-Score.")
            else:
                st.info("Keine Daten für diesen Filter vorhanden.")

        else:
            # Alte Logik: Reine Signal-Quote
            st.markdown(
                f"### 🏆 Irma: Top 10 Sektoren nach Signal-Quote ({signal_choice})"
            )
            if not sector_base.empty:
                chart = (
                    alt.Chart(sector_base)
                    .mark_bar(color="#10b981")
                    .encode(
                        x=alt.X(
                            "signal_quota_percent:Q",
                            title="Signal-Quote (%)",
                            axis=alt.Axis(format=".1f"),
                        ),
                        y=alt.Y(
                            "sector:N",
                            sort="-x",
                            title="Sektor",
                            axis=alt.Axis(values=sector_base["sector"].tolist()),
                        ),
                        tooltip=[
                            "sector",
                            alt.Tooltip(
                                "signal_quota_percent:Q", format=".1f", title="Quote (%)"
                            ),
                            alt.Tooltip("signal_tickers:Q", title="Ticker mit Signal"),
                            alt.Tooltip(
                                "total_tickers:Q", title="Gesamt Ticker im Sektor"
                            ),
                        ],
                    )
                    .properties(height=420)
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info(
                    "Irma konnte für diese Filterkombination keine Sektor-Daten berechnen."
                )

        st.markdown("---")

        # --- TABS FÜR DIE EINZELNEN KATEGORIEN ---
        (
            tab_favs,
            tab_ema20_elite,
            tab_ema20,
            tab_unter_elite,
            tab_unter_ema20,
            tab_gesamt,
            tab_dip,
        ) = st.tabs([
            "⭐ Favoriten",
            "🟣 EMA20+ELITE",
            "🟢 EMA20",
            "🟡 unter EMA20+ELITE",
            "🔴 unter EMA20",
            "📁 Gesamtliste",
            "📉 Dip-Scanner",
        ])

        def show_table(df_subset, category_type="default", is_total_view=False):
            d = df_subset.copy()
            if d.empty:
                st.info("Keine Daten für diese Filtereinstellung vorhanden.")
                return

            d["Action"] = False

            def get_company_prefix(row):
                sig = str(row.get("signal_type", "")).strip().lower()
                dist = row.get("EMA20_Dist_%", None)

                is_above_ema = False if pd.isna(dist) else (dist >= 0)
                is_el = "elite" in sig

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
                elif category_type == "gesamt":
                    if is_el:
                        return (
                            f"🟣 {row.get('company_name', '')}"
                            if is_above_ema
                            else f"🟡 {row.get('company_name', '')}"
                        )
                    else:
                        return (
                            f"🟢 {row.get('company_name', '')}"
                            if is_above_ema
                            else f"🔴 {row.get('company_name', '')}"
                        )
                else:
                    return f"{row.get('company_name', '')}"

            d["company_name_formatted"] = d.apply(get_company_prefix, axis=1)

            if is_total_view:
                d["⭐"] = d["is_favorite"].apply(lambda x: "⭐" if x else "")
                cols = [
                    "⭐",
                    "Action",
                    "company_name_formatted",
                    "Chart",
                    "Performance (%)",
                    "candle_time",
                    "sector",
                    "signal_type",
                    "gettex_ticker",
                ]
            else:
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
                "⭐": st.column_config.TextColumn("⭐", width="small"),
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

        # Tab 1: Favoriten
        with tab_favs:
            show_table(df[df["is_favorite"] == True], category_type="favorites")

        # Tab 2: EMA20 + ELITE
        with tab_ema20_elite:
            show_table(
                df[
                    (df["EMA20_Dist_%"].notna())
                    & (df["EMA20_Dist_%"] >= 0)
                    & (df["signal_type"].apply(is_elite))
                ],
                category_type="ema20_elite",
            )

        # Tab 3: EMA20
        with tab_ema20:
            show_table(
                df[
                    (df["EMA20_Dist_%"].notna())
                    & (df["EMA20_Dist_%"] >= 0)
                    & (~df["signal_type"].apply(is_elite))
                ],
                category_type="ema20",
            )

        # Tab 4: unter EMA20 + ELITE
        with tab_unter_elite:
            show_table(
                df[
                    (df["EMA20_Dist_%"].isna() | (df["EMA20_Dist_%"] < 0))
                    & (df["signal_type"].apply(is_elite))
                ],
                category_type="unter_elite",
            )

        # Tab 5: unter EMA20
        with tab_unter_ema20:
            show_table(
                df[
                    (df["EMA20_Dist_%"].isna() | (df["EMA20_Dist_%"] < 0))
                    & (~df["signal_type"].apply(is_elite))
                ],
                category_type="unter_ema20",
            )

        # Tab 6: Gesamtliste
        with tab_gesamt:
            show_table(df, category_type="gesamt", is_total_view=True)

        # --- TAB: DIP-SCANNER ---
        with tab_dip:
            st.subheader(
                "📉 Dip-Scanner: Aktien mit $\\ge$ 20% Korrektur vom Allzeithoch"
            )
            st.markdown(
                "Solide Werte aus deiner Watchlist (ohne Risk-Werte), die sich in einer tieferen"
                " Konsolidierung befinden."
            )

            try:
                dip_response = (
                    supabase.table("watchlist")
                    .select(
                        "ticker, company_name, sector, gettex_ticker, current_price,"
                        " ath, distance_from_ath, strategy_kategorie"
                    )
                    .lte("distance_from_ath", -20.0)
                    .neq("strategy_kategorie", "risk")
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