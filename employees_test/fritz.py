from datetime import datetime
import os
import pandas as pd
from db import get_db_client
import yfinance as yf

# Verbindung zu Supabase via zentralem db-Modul
supabase = get_db_client()


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
    
    # Alle Spaltennamen in lowercase umwandeln, um Case-Sensitivity-Probleme auszuschließen
    df_watchlist.columns = [str(c).lower() for c in df_watchlist.columns]
    print(f"📊 {len(df_watchlist)} Zeilen aus watchlist geladen. Spalten: {df_watchlist.columns.tolist()}")

    processed_results = []

    for _, row in df_watchlist.iterrows():
        ticker = (
            row.get("ticker") 
            or row.get("symbol") 
            or row.get("aktie")
        )
        if not ticker:
            print(f"⚠️ Überspringe Zeile: Kein Ticker gefunden in {dict(row)}")
            continue

        name = row.get("name") or row.get("company_name") or ticker
        sektor = row.get("strategy_kategorie") or row.get("sector") or row.get("sektor") or "Standard"

        # Robuste Fallbacks aus der Datenbank holen, falls yfinance streikt
        db_preis = float(
            row.get("current_price")
            or row.get("aktueller_preis")
            or 0.0
        )
        eps = float(row.get("eps", 0.0))
        fcf_per_share = float(row.get("fcf_je_aktie", 0.0))

        preis = db_preis
        wachstum = 5.0

        try:
            stock = yf.Ticker(str(ticker).strip())
            info = stock.info

            live_preis = float(
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or 0.0
            )
            if live_preis > 0:
                preis = live_preis

            live_eps = float(info.get("trailingEps") or info.get("forwardEps") or 0.0)
            if live_eps != 0:
                eps = live_eps

            # Free Cash Flow je Aktie berechnen
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
                if info.get("freeCashflow") and info.get("sharesOutstanding"):
                    fcf_per_share = float(info.get("freeCashflow")) / float(info.get("sharesOutstanding"))

            if info.get("earningsGrowth"):
                wachstum = float(info.get("earningsGrowth")) * 100

        except Exception as e:
            print(f"⚠️ Hinweis bei Ticker {ticker} (Nutze DB-Fallbacks): {e}")

        if preis <= 0:
            print(f"⏭️ Überspringe {ticker}: Kein gültiger Preis (0.0 oder ungültig).")
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
            "ticker": str(ticker).strip().upper(),
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

    # 2. In die separate Cache-Tabelle schreiben
    if processed_results:
        try:
            supabase.table("fair_value_cache").delete().neq(
                "ticker", "DUMMY"
            ).execute()
            supabase.table("fair_value_cache").insert(processed_results).execute()
            print(
                f"✅ Fritz hat {len(processed_results)} Titel erfolgreich aufbereitet und in Supabase hinterlegt!"
            )
        except Exception as e:
            print(f"❌ Fehler beim Speichern durch Fritz in Supabase: {e}")
    else:
        print("⚠️ Keine berechneten Ergebnisse zum Speichern vorhanden.")


if __name__ == "__main__":
    fritz_run_daily_prep()