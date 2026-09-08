from datetime import datetime
import pandas as pd
import yfinance as yf


class FairValueScreener:

  def __init__(self, supabase_client):
    self.supabase = supabase_client

  def calculate_fair_value_batch(self):
    """Berechnet für alle Watchlist-Werte einen gewichteten Fair Value (Multi-Model Blend)."""
    try:
      watchlist_res = self.supabase.table("watchlist").select("*").execute()
      watchlist_df = pd.DataFrame(watchlist_res.data)

      if watchlist_df.empty or "ticker" not in watchlist_df.columns:
        return pd.DataFrame()

      results = []
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

          # 1. KGV-Modell
          model_pe_val = None
          if eps and eps > 0:
            target_pe = 18.0
            model_pe_val = eps * target_pe

          # 2. Buchwert-Modell
          model_pb_val = None
          if book_value and book_value > 0:
            model_pb_val = book_value * 2.0

          # 3. DCF / FCF-Modell
          model_dcf_val = None
          if fcf and shares and shares > 0 and fcf > 0:
            fcf_per_share = fcf / shares
            model_dcf_val = fcf_per_share * 14.0

          valid_models = [
              m
              for m in [model_pe_val, model_pb_val, model_dcf_val]
              if m and m > 0
          ]
          fair_value = (
              sum(valid_models) / len(valid_models) if valid_models else 0
          )

          if fair_value and fair_value > 0:
            upside_pct = ((fair_value - current_price) / current_price) * 100

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

          results.append({
              "Ticker": ticker,
              "Name": info.get("shortName", ticker),
              "Sektor": info.get("sector", "N/A"),
              "Aktueller Preis": round(current_price, 2),
              "Fair Value (Est.)": (
                  round(fair_value, 2) if fair_value else "N/A"
              ),
              "Potential (%)": (
                  f"{round(upside_pct, 1)}%" if fair_value else "N/A"
              ),
              "Status": status,
          })
        except Exception:
          continue

      return pd.DataFrame(results)
    except Exception as e:
      print(f"Fehler im Screener: {e}")
      return pd.DataFrame()