from datetime import datetime, timezone
import pandas as pd
import yfinance as yf


class FairValueScreener:

  def __init__(self, supabase_client):
    self.supabase = supabase_client

  def get_or_calculate_fair_values(self, force_refresh=False):
    """Prüft, ob heute schon Werte da sind. Wenn nicht oder bei force_refresh, neu berechnen."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
      if not force_refresh:
        # Prüfen ob Daten von heute existieren
        res = (
            self.supabase.table("fair_value_cache")
            .select("*")
            .gte("updated_at", f"{today_str}T00:00:00")
            .execute()
        )
        if res.data and len(res.data) > 0:
          # Aus Cache laden
          df = pd.DataFrame(res.data)
          # Spalten für die UI umbenennen / anpassen
          df = df.rename(
              columns={
                  "ticker": "Ticker",
                  "name": "Name",
                  "sektor": "Sektor",
                  "aktueller_preis": "Aktueller Preis",
                  "fair_value": "Fair Value (Est.)",
                  "potential_pct": "Potential (%)",
                  "status": "Status",
              }
          )
          # Potential in Prozent-String formatieren falls nötig
          df["Potential (%)"] = df["Potential (%)"].apply(
              lambda x: f"{x}%" if pd.notnull(x) else "N/A"
          )
          return df, False  # Stammt aus Cache
    except Exception:
      pass

    # Wenn keine Daten da sind oder erzwungen: Neu berechnen
    df_fresh = self.calculate_and_store_batch()
    return df_fresh, True  # Neu berechnet

  def calculate_and_store_batch(self):
    """Berechnet alles frisch, schreibt es in die DB und gibt das DataFrame zurück."""
    try:
      watchlist_res = self.supabase.table("watchlist").select("*").execute()
      watchlist_df = pd.DataFrame(watchlist_res.data)

      if watchlist_df.empty or "ticker" not in watchlist_df.columns:
        return pd.DataFrame()

      results = []
      rows_to_insert = []
      now_iso = datetime.now(timezone.utc).isoformat()

      for _, row in watchlist_df.iterrows():
        ticker = row.get("ticker")
        try:
          t = yf.Ticker(ticker)
          info = t.info

          current_price = info.get(
              "currentPrice", info.get("regularMarketPrice", 0)
          )
          if not current_price or current_price == 0:
            hist = t.history(period="1d")
            if not hist.empty:
              current_price = hist["Close"].iloc[-1]
            else:
              continue

          eps = info.get("trailingEps")
          book_value = info.get("bookValue")
          fcf = info.get("freeCashflow")
          shares = info.get("sharesOutstanding")

          # Modelle
          model_pe_val = (eps * 18.0) if (eps and eps > 0) else None
          model_pb_val = (book_value * 2.0) if (book_value and book_value > 0) else None
          model_dcf_val = (
              ((fcf / shares) * 14.0)
              if (fcf and shares and shares > 0 and fcf > 0)
              else None
          )

          valid_models = [
              m
              for m in [model_pe_val, model_pb_val, model_dcf_val]
              if m and m > 0
          ]
          fair_value = (
              sum(valid_models) / len(valid_models) if valid_models else 0
          )

          if fair_value and fair_value > 0:
            upside_pct = round(
                ((fair_value - current_price) / current_price) * 100, 1
            )

            if upside_pct > 15:
              status = "🟢 Stark Unterbewertet"
            elif upside_pct > 5:
              status = "🟢 Leicht Unterbewertet"
            elif upside_pct >= -5:
              status = "🟡 Fair bewertet"
            elif upside_pct >= -15:
              status = "🟠 Leicht Überbewertet"
            else:
              status = "🔴 Stark Überbewertet"
          else:
            fair_value = 0
            upside_pct = 0
            status = "⚪ Keine Daten"

          name = info.get("shortName", ticker)
          sektor = info.get("sector", "N/A")

          # Für UI
          results.append({
              "Ticker": ticker,
              "Name": name,
              "Sektor": sektor,
              "Aktueller Preis": round(current_price, 2),
              "Fair Value (Est.)": round(fair_value, 2) if fair_value else 0,
              "Potential (%)": f"{upside_pct}%" if fair_value else "N/A",
              "Status": status,
          })

          # Für Supabase Cache (alte Einträge für diesen Ticker vorher löschen oder upserten)
          rows_to_insert.append({
              "ticker": ticker,
              "name": name,
              "sektor": sektor,
              "aktueller_preis": round(current_price, 2),
              "fair_value": round(fair_value, 2) if fair_value else 0,
              "potential_pct": upside_pct,
              "status": status,
              "updated_at": now_iso,
          })
        except Exception:
          continue

      # In Supabase speichern (Alten Cache leeren und neu befüllen oder per Upsert)
      if rows_to_insert:
        try:
          # Wir leeren die Tabelle für einen sauberen Tagesstand
          self.supabase.table("fair_value_cache").delete().neq(
              "ticker", "DUMMY"
          ).execute()
          self.supabase.table("fair_value_cache").insert(
              rows_to_insert
          ).execute()
        except Exception as db_err:
          print(f"Fehler beim Caching in Supabase: {db_err}")

      return pd.DataFrame(results)
    except Exception as e:
      print(f"Fehler im Screener: {e}")
      return pd.DataFrame()