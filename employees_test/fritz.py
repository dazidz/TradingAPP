from datetime import datetime
import os
import pandas as pd
from supabase import create_client
import yfinance as yf

# Verbindung zu Supabase (Nutzt Secrets oder Umgebungsvariablen)
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(URL, KEY)


def fritz_run_daily_prep():
    print("🤖 Fritz übernimmt die Schicht und bereitet die Daten auf...")

    # 1. Watchlist aus Supabase laden (mit explizitem public-Schema gegen PGRST125)
    try:
        response = supabase.schema("public").table("watchlist").select("*").execute()
    except Exception as e:
        print(f"❌ Fehler beim Laden der Watchlist: {e}")
        return

    if not response.data:
        print("⚠️ Keine Watchlist-Einträge gefunden.")
        return

    df_watchlist = pd.DataFrame(response.data)
    processed_results = []

    for _, row in df_watchlist.iterrows():
        ticker = (
            row.get("ticker") or row.get("symbol") or row.get("aktie")
        )
        if not ticker:
            continue

        name = row.get("name", ticker)
        sektor = row.get("strategy_kategorie", row.get("sektor", "Standard"))

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            preis = float(
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or row.get("aktueller_preis")
                or 0.0
            )
            eps = float(info.get("trailingEps") or info.get("forwardEps") or 0.0)

            # Free Cash Flow je Aktie berechnen
            fcf_per_share = 0.0
            try:
                cf_stmt = stock.cashflow
                if cf_stmt is not None and not cf_stmt.empty:
                    op_cf = cf_stmt.loc["Operating Cash Flow"].iloc[0]
                    capex = abs(
                        cf_stmt.loc["Capital Expenditure"].iloc[0]
                        if "Capital Expenditure" in cf_stmt.index
                        else 0.0
                    )
                    shares = float(info.get("sharesOutstanding") or 1.0)
                    if shares > 0:
                        fcf_per_share = (op_cf - capex) / shares
            except Exception:
                fcf_per_share = float(info.get("freeCashflow", 0.0)) / float(
                    info.get("sharesOutstanding", 1.0)
                )

            wachstum = float(
                info.get("earningsGrowth", 0.08) * 100
                if info.get("earningsGrowth")
                else 5.0
            )

        except Exception as e:
            print(f"Fehler bei {ticker} durch Fritz: {e}")
            preis = float(row.get("aktueller_preis", 0.0))
            eps = float(row.get("eps", 0.0))
            fcf_per_share = float(row.get("fcf_je_aktie", 0.0))
            wachstum = 5.0

        if preis <= 0:
            continue

        # Graham-Formel & Buffett Owner Earnings berechnen
        graham = eps * (8.5 + (2 * max(0.0, wachstum))) if eps > 0 else preis
        buffett = (fcf_per_share / 0.10) if fcf_per_share > 0 else graham
        fair_value = (graham * 0.6) + (buffett * 0.4)
        potential = ((fair_value - preis) / preis) * 100

        if potential >= 30:
            status = "🟢 Stark Unterbewertet"
        elif potential >= 10:
            status = "🟢 Unterbewertet"
        elif potential >= -15:
            status = "🟡 Fair Bewertet"
        else:
            status = "🔴 Überbewertet"

        processed_results.append({
            "ticker": ticker,
            "name": name,
            "sektor": sektor,
            "aktueller_preis": round(preis, 2),
            "fair_value": round(fair_value, 2),
            "potential_pct": round(potential, 1),
            "status": status,
            "eps": round(eps, 2),
            "fcf_aktie": round(fcf_per_share, 2),
            "updated_at": datetime.now().isoformat(),
        })

    # 2. In die separate Cache-Tabelle schreiben (ebenfalls mit explizitem public-Schema)
    if processed_results:
        try:
            supabase.schema("public").table("fair_value_cache").delete().neq(
                "ticker", "DUMMY"
            ).execute()
            supabase.schema("public").table("fair_value_cache").insert(processed_results).execute()
            print(
                f"✅ Fritz hat {len(processed_results)} Titel erfolgreich aufbereitet und in Supabase hinterlegt!"
            )
        except Exception as e:
            print(f"❌ Fehler beim Speichern durch Fritz in Supabase: {e}")


if __name__ == "__main__":
    fritz_run_daily_prep()