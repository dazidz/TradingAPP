from datetime import datetime, timezone
import pandas as pd
import yfinance as yf


class FairValueScreener:

  def __init__(self, supabase_client):
    self.supabase = supabase_client

  def get_or_calculate_fair_values(self, force_refresh=False):
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
      if not force_refresh:
        res = (
            self.supabase.table("fair_value_cache")
            .select("*")
            .gte("updated_at", f"{today_str}T00:00:00")
            .execute()
        )
        if res.data and len(res.data) > 0:
          df = pd.DataFrame(res.data)
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
          df["Potential (%)"] = df["Potential (%)"].apply(
              lambda x: f"{x}%" if pd.notnull(x) else "N/A"
          )
          return df, False
    except Exception:
      pass

    df_fresh = self.calculate_and_store_batch()
    return df_fresh, True

  def calculate_and_store_batch(self):
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

          model_pe_val = None
          model_pb_val = None
          model_dcf_val = None

          # 1. KGV-Modell (konservativ gedauert: max KGV von 18 angesetzt)
          if eps and eps > 0 and eps < current_price:
            raw_pe = info.get("trailingPE", 15)
            target_pe = min(
                raw_pe if raw_pe and raw_pe > 0 else 15, 18.0
            )  # Reales KGV oder max 18
            model_pe_val = eps * target_pe

          # 2. Buchwert-Modell (konservativ: P/B max 1.5)
          if book_value and book_value > 0:
            model_pb_val = book_value * 1.5

          # 3. FCF-Modell (konservativ: FCF-Rendite von min 8% angestrebt -> Multiplikator 12.5)
          if fcf and shares and shares > 0 and fcf > 0:
            fcf_per_share = fcf / shares
            model_dcf_val = fcf_per_share * 12.5

          valid_models = [
              m
              for m in [model_pe_val, model_pb_val, model_dcf_val]
              if m and m > 0
          ]

          if valid_models:
            raw_fair_value = sum(valid_models) / len(valid_models)

            # SICHERHEITS-CAP: Fair Value max 2.5x des aktuellen Preises
            max_allowed_fv = current_price * 2.5
            fair_value = min(raw_fair_value, max_allowed_fv)
          else:
            fair_value = 0

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

          results.append({
              "Ticker": ticker,
              "Name": name,
              "Sektor": sektor,
              "Aktueller Preis": round(current_price, 2),
              "Fair Value (Est.)": round(fair_value, 2) if fair_value else 0,
              "Potential (%)": f"{upside_pct}%" if fair_value else "N/A",
              "Status": status,
          })

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

      if rows_to_insert:
        try:
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