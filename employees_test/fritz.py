from datetime import datetime
import math
import os
import pandas as pd
from db import get_db_client
import yfinance as yf

# Verbindung zu Supabase via zentralem db-Modul
supabase = get_db_client()


def clean_float(val, default=0.0):
    """Konvertiert Werte in saubere, JSON-konforme Floats (keine NaN oder inf)."""
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def fritz_run_daily_prep():
    print("🤖 Fritz übernimmt die Schicht und bereitet die Daten auf...")

    # 1. Watchlist aus Supabase laden
    try:
        response = supabase.table("watchlist").select("*").execute()
    except Exception as e:
        print(f"❌ Fehler beim Laden der Watchlist: {e}")
        return

    if not response.data:
        print("⚠️ Keine Watchlist-Einträge gefunden.")
        return

    df_watchlist = pd.DataFrame(response.data)
    df_watchlist.columns = [str(c).lower() for c in df_watchlist.columns]
    print(f"📊 {len(df_watchlist)} Zeilen aus watchlist geladen.")

    processed_results = []

    for _, row in df_watchlist.iterrows():
        ticker = (
            row.get("ticker") 
            or row.get("symbol") 
            or row.get("aktie")
        )
        if not ticker:
            continue

        name = row.get("name") or row.get("company_name") or ticker
        sektor = row.get("strategy_kategorie") or row.get("sector") or row.get("sektor") or "Standard"

        db_preis = clean_float(row.get("current_price") or row.get("aktueller_preis"), 0.0)
        eps = clean_float(row.get("eps"), 0.0)
        fcf_per_share = clean_float(row.get("fcf_je_aktie"), 0.0)

        preis = db_preis
        analyst_target = 0.0
        raw_growth = 0.05  # Standard: 5%

        try:
            stock = yf.Ticker(str(ticker).strip())
            info = stock.info

            live_preis = clean_float(info.get("currentPrice") or info.get("regularMarketPrice"), 0.0)
            if live_preis > 0:
                preis = live_preis

            live_eps = clean_float(info.get("trailingEps") or info.get("forwardEps"), 0.0)
            if live_eps != 0:
                eps = live_eps

            # Analysten-Kursziel (targetMeanPrice) von yfinance abgreifen
            analyst_target = clean_float(info.get("targetMeanPrice"), 0.0)

            # Free Cash Flow je Aktie berechnen
            try:
                cf_stmt = stock.cashflow
                if cf_stmt is not None and not cf_stmt.empty:
                    op_cf = clean_float(cf_stmt.loc["Operating Cash Flow"].iloc[0], 0.0)
                    capex = abs(
                        clean_float(cf_stmt.loc["Capital Expenditure"].iloc[0], 0.0)
                        if "Capital Expenditure" in cf_stmt.index
                        else 0.0
                    )
                    shares = clean_float(info.get("sharesOutstanding"), 1.0)
                    if shares > 0:
                        fcf_per_share = (op_cf - capex) / shares
            except Exception:
                fc_flow = clean_float(info.get("freeCashflow"), 0.0)
                shares_out = clean_float(info.get("sharesOutstanding"), 0.0)
                if fc_flow != 0 and shares_out > 0:
                    fcf_per_share = fc_flow / shares_out

            if info.get("earningsGrowth"):
                raw_growth = clean_float(info.get("earningsGrowth"), 0.05)

        except Exception as e:
            # yfinance HTTP Errors (wie bei ungültigen Tickern) leise abfangen
            pass

        if preis <= 0:
            continue

        # --- 1. WACHSTUM SAUBER DECKELN (CAP BEI MAX 12% p.a.) ---
        # Verhindert, dass z.B. 900% YoY-Quartalssprünge die Formel sprengen
        wachstum = max(0.0, min(raw_growth * 100, 12.0))

        # --- 2. GRAHAM-FORMEL MIT KGV-CAP ---
        # Multiplikator (8.5 + 2*g) bei KGV 30 deckeln
        graham_multiplier = min(8.5 + (2 * wachstum), 30.0)
        graham = eps * graham_multiplier if eps > 0 else preis

        # --- 3. BUFFETT OWNER EARNINGS (FCF-Ansatz) ---
        buffett = (fcf_per_share / 0.10) if fcf_per_share > 0 else graham

        # --- 4. HYBRID-MODELLVERSCHMELZUNG ---
        if analyst_target > 0:
            fundamentaler_wert = (graham * 0.6) + (buffett * 0.4)
            fair_value = (fundamentaler_wert * 0.7) + (analyst_target * 0.3)
        else:
            fair_value = (graham * 0.6) + (buffett * 0.4)

        # --- 5. EXTREMA-SCHUTZ GEGEN MODELLAUSREISSER ---
        # Fair Value darf maximal zwischen dem 0.3-fachen und 2.5-fachen des aktuellen Kurses liegen
        max_allowed_fv = preis * 2.5
        min_allowed_fv = preis * 0.3
        fair_value = max(min_allowed_fv, min(fair_value, max_allowed_fv))

        potential = ((fair_value - preis) / preis) * 100

        # Werte final absichern gegen NaN / inf
        preis = clean_float(preis, 0.0)
        fair_value = clean_float(fair_value, preis)
        potential = clean_float(potential, 0.0)
        eps = clean_float(eps, 0.0)
        fcf_per_share = clean_float(fcf_per_share, 0.0)

        # Status festlegen
        if potential >= 30:
            status = "🟢 Stark Unterbewertet"
        elif potential >= 10:
            status = "🟢 Unterbewertet"
        elif potential >= -15:
            status = "🟡 Fair Bewertet"
        else:
            status = "🔴 Überbewertet"

        processed_results.append({
            "ticker": str(ticker).strip().upper(),
            "name": str(name),
            "sektor": str(sektor),
            "aktueller_preis": round(preis, 2),
            "fair_value": round(fair_value, 2),
            "potential_pct": round(potential, 1),
            "status": status,
            "eps": round(eps, 2),
            "fcf_aktie": round(fcf_per_share, 2),
            "updated_at": datetime.now().isoformat(),
        })

    # 2. In die Supabase-Cache-Tabelle schreiben (in Chunks von 500)
    if processed_results:
        try:
            supabase.table("fair_value_cache").delete().neq(
                "ticker", "DUMMY"
            ).execute()
            
            chunk_size = 500
            for i in range(0, len(processed_results), chunk_size):
                chunk = processed_results[i:i + chunk_size]
                supabase.table("fair_value_cache").insert(chunk).execute()

            print(
                f"✅ Fritz hat {len(processed_results)} Titel erfolgreich aufbereitet und in Supabase hinterlegt!"
            )
        except Exception as e:
            print(f"❌ Fehler beim Speichern durch Fritz in Supabase: {e}")
    else:
        print("⚠️ Keine berechneten Ergebnisse zum Speichern vorhanden.")


if __name__ == "__main__":
    fritz_run_daily_prep()