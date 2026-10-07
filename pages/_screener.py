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

# --- IRMA SEKTOR FILTER AUSWAHL ---
col_filter1, col_filter2 = st.columns([2, 3])
with col_filter1:
    signal_choice = st.selectbox(
        "🎯 Filter für Irma Sektor-Analyse:",
        options=["ALL", "ELITE", "ELITE_EMA", "KAUF", "KAUF_EMA"],
        format_func=lambda x: {
            "ALL": "Alle Signale",
            "ELITE": "Elite Signale",
            "ELITE_EMA": "Elite + Über EMA20",
            "KAUF": "Kauf Signale",
            "KAUF_EMA": "Kauf + Über EMA20"
        }[x]
    )

# Sektor-Daten entsprechend der Auswahl laden
sector_df = irma.get_top_sector_quotas(signal_filter=signal_choice)

st.markdown(f"### 🏆 Irma: Top 10 Sektoren nach Signal-Quote ({signal_choice})")
if not sector_df.empty:
    chart = (
        alt.Chart(sector_df)
        .mark_bar(color="#10b981")
        .encode(
            x=alt.X("signal_quota_percent:Q", title="Signal-Quote (%)", axis=alt.Axis(format=".1f")),
            y=alt.Y(
                "sector:N", 
                sort="-x", 
                title="Sektor",
                axis=alt.Axis(values=sector_df['sector'].tolist())
            ),
            tooltip=[
                "sector",
                alt.Tooltip("signal_quota_percent:Q", format=".1f", title="Quote (%)"),
                alt.Tooltip("signal_tickers:Q", title="Ticker mit Signal"),
                alt.Tooltip("total_tickers:Q", title="Gesamt Ticker im Sektor"),
            ],
        )
        .properties(height=420)
    )
    st.altair_chart(chart, use_container_width=True)
else:
    st.info("Irma konnte für diese Filterkombination keine Sektor-Daten berechnen.")

st.markdown("---")


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

        # Tabs für die einzelnen Kategorien inklusive Gesamtliste
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

            # Präfix-Logik mit striktem Fallback bei fehlendem EMA20 (NaN -> wird wie unter EMA20 behandelt)
            def get_company_prefix(row):
                sig = str(row.get("signal_type", "")).strip().lower()
                dist = row.get("EMA20_Dist_%", None)
                
                # Wenn dist NaN/None ist, gilt EMA20 strikt als FALSE (< 0)
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
                "signal_type": st.column_config.TextColumn