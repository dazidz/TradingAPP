import pandas as pd
import numpy as np
from datetime import datetime

class FairValueScreener:
    def __init__(self, supabase_client):
        self.supabase = supabase_client

    def get_or_calculate_fair_values(self, force_refresh=False):
        """
        Lädt die Watchlist und fundamentale Kennzahlen, berechnet den Fair Value
        nach Graham-Formel & Owner Earnings (Buffett) und gibt ein strukturiertes DataFrame zurück.
        """
        try:
            # 1. Watchlist und fundamentale Daten laden
            # Wir gehen davon aus, dass in der Watchlist oder einer zugehörigen Tabelle 
            # Kennzahlen wie eps, buchwert (bvps), fcf und aktueller_preis liegen.
            response = self.supabase.table("watchlist").select("*").execute()
            if not response.data:
                return pd.DataFrame(), False
            
            df = pd.DataFrame(response.data)
            
            results = []
            for _, row in df.iterrows():
                ticker = row.get("ticker") or row.get("symbol")
                name = row.get("name", ticker)
                sektor = row.get("strategy_kategorie", row.get("sektor", "Standard"))
                
                # Rohdaten absichern (Fallbacks, falls Spaltennamen leicht abweichen)
                preis = float(row.get("aktueller_preis") or row.get("preis") or row.get("price") or 0.0)
                eps = float(row.get("eps") or row.get("gewinn_je_aktie") or 0.0)
                bvps = float(row.get("buchwert_je_aktie") or row.get("book_value") or 0.0)
                fcf_je_aktie = float(row.get("fcf_je_aktie") or row.get("free_cash_flow_per_share") or 0.0)
                wachstum_g = float(row.get("erwartetes_wachstum") or row.get("growth_rate") or 5.0) # Standard 5% konservativ
                
                if preis <= 0:
                    continue

                # --- 1. BENJAMIN GRAHAM FORMEL ---
                # V = EPS * (8.5 + 2 * g)
                # 8.5 ist das Basis-KGV für ein Unternehmen ohne Wachstum
                graham_val = eps * (8.5 + (2 * max(0.0, wachstum_g))) if eps > 0 else 0.0

                # --- 2. WARREN BUFFETT / OWNER EARNINGS MODELL ---
                # Diskontierter Free Cash Flow (vereinfacht als perpetuity mit 10% Hurdle Rate)
                # Fair Value = Fcf_je_aktie / 0.10 (entspricht einem 10er Multiplikator auf den FCF)
                owner_earnings_val = (fcf_je_aktie / 0.10) if fcf_je_aktie > 0 else 0.0

                # --- 3. BLENDED FAIR VALUE (GEWICHTUNG) ---
                # Wenn beide Modelle Daten liefern, gewichten wir sie. Ansonsten das verfügbare Modell.
                valid_vals = [v for v in [graham_val, owner_earnings_val] if v > 0]
                if len(valid_vals) == 2:
                    fair_value = (graham_val * 0.6) + (owner_earnings_val * 0.4)
                elif len(valid_vals) == 1:
                    fair_value = valid_vals[0]
                else:
                    # Fallback über Buchwert (Graham Substanzwert-Ansatz) falls keine Ertragsdaten da sind
                    fair_value = bvps * 1.2 if bvps > 0 else preis

                # --- 4. POTENTIAL & STATUS (MARGIN OF SAFETY) ---
                if fair_value > 0:
                    potential_pct = ((fair_value - preis) / preis) * 100
                else:
                    potential_pct = 0.0

                # Status-Klassifizierung nach Value-Kriterien
                if potential_pct >= 30:
                    status = "🟢 Stark Unterbewertet"
                elif potential_pct >= 10:
                    status = "🟢 Unterbewertet"
                elif potential_pct >= -15:
                    status = "🟡 Fair Bewertet"
                else:
                    status = "🔴 Überbewertet"

                results.append({
                    "Ticker": ticker,
                    "Name": name,
                    "Sektor": sektor,
                    "Aktueller Preis": round(preis, 2),
                    "Fair Value (Est.)": round(fair_value, 2),
                    "Potential (%)": round(potential_pct, 1),
                    "Status": status,
                    "Graham Value": round(graham_val, 2),
                    "Owner Earnings Val": round(owner_earnings_val, 2)
                })

            df_result = pd.DataFrame(results)
            if not df_result.empty:
                df_result = df_result.sort_values(by="Potential (%)", ascending=False)

            return df_result, True

        except Exception as e:
            print(f"Fehler bei Fair-Value-Berechnung: {e}")
            return pd.DataFrame(), False