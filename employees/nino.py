from datetime import datetime, timedelta
import json
import os
from db import get_db_client
import pandas as pd
import yfinance as yf


class NinoSignalsAssistant:

  def __init__(self, supabase_client):
    self.supabase = supabase_client
    self.table_active_signals = "signals"
    self.table_signals_journal = "signals_journal"
    self.table_joris_journal = "joris_journal"
    self.table_aris_arbeitsspeicher = "aris_arbeitsspeicher"
    self.table_favorites = "favorites"

  def is_valid_ticker(self, ticker):
    """Prüft, ob ein Ticker ein gültiges Börsensymbol ist und keine Platzhalter/Systemnamen."""
    if not ticker or not isinstance(ticker, str):
      return False
    t_upper = ticker.strip().upper()
    invalid_keywords = ["SYNTHESIS", "AUTO_SWING", "PLACEHOLDER", "TEST"]
    if any(kw in t_upper for kw in invalid_keywords):
      return False
    if len(t_upper) > 15 or " " in t_upper:
      return False
    return True

  def _get_favorite_tickers(self):
    """Lädt alle Favoriten-Ticker aus der Datenbank."""
    favorite_tickers = set()
    try:
      fav_res = (
          self.supabase.table(self.table_favorites).select("ticker").execute()
      )
      if fav_res.data:
        favorite_tickers = {
            row["ticker"].upper() for row in fav_res.data if row.get("ticker")
        }
    except Exception as e:
      print(f"Fehler beim Laden der Favoriten: {e}")
    return favorite_tickers

  def _parse_meta_data(self, sig_obj):
    """Extrahiert Meta-Daten wie SMI, ADX und EMA20."""
    meta_raw = sig_obj.get("meta_data", "{}")
    smi_val, adx_val = None, None
    above_ema = False
    try:
      if isinstance(meta_raw, str):
        meta_dict = json.loads(meta_raw.replace("'", '"'))
      elif isinstance(meta_raw, dict):
        meta_dict = meta_raw
      else:
        meta_dict = {}

      smi_val = meta_dict.get("smi")
      adx_val = meta_dict.get("adx")
      above_ema = bool(meta_dict.get("above_ema20", False))
    except Exception:
      pass
    return (
        float(smi_val) if smi_val is not None else None,
        float(adx_val) if adx_val is not None else None,
        above_ema,
    )

  def _fetch_5d_performance(self, ticker, sig_date, base_preis):
    """Zieht über yfinance die Kursdaten ab sig_date und berechnet 5-Tage Max- & End-Performance inkl. Kerzen-Zeitstempel des Max-Werts."""
    try:
      end_date_fetch = sig_date + timedelta(days=15)
      df_hist = yf.download(
          ticker,
          start=sig_date.strftime("%Y-%m-%d"),
          end=end_date_fetch.strftime("%Y-%m-%d"),
          progress=False,
          auto_adjust=True,
      )

      if df_hist.empty:
        return None

      def get_col(df, col_name):
        if col_name not in df:
          return None
        c = df[col_name]
        if isinstance(c, pd.DataFrame):
          c = c.iloc[:, 0]
        return c

      close_s = get_col(df_hist, "Close")
      high_s = get_col(df_hist, "High")

      if close_s is None or close_s.empty:
        return None

      if base_preis <= 0:
        base_preis = float(close_s.iloc[0])

      df_5d = df_hist.head(5)
      high_5d_s = get_col(df_5d, "High")
      close_5d_s = get_col(df_5d, "Close")

      high_5d = (
          float(high_5d_s.max())
          if high_5d_s is not None and not high_5d_s.empty
          else base_preis
      )
      close_5d = (
          float(close_5d_s.iloc[-1])
          if close_5d_s is not None and not close_5d_s.empty
          else base_preis
      )

      # Ermittlung des genauen Kerzen-Zeitstempels, an dem das Maximum aufgetreten ist
      candle_time_max = None
      if high_5d_s is not None and not high_5d_s.empty:
        max_idx = high_5d_s.idxmax()
        if pd.notnull(max_idx):
          candle_time_max = pd.to_datetime(max_idx).isoformat()

      max_perf_5d = (
          round(((high_5d - base_preis) / base_preis) * 100, 2)
          if base_preis > 0
          else 0
      )
      end_perf_5d = (
          round(((close_5d - base_preis) / base_preis) * 100, 2)
          if base_preis > 0
          else 0
      )

      return {
          "base_preis": base_preis,
          "max_kurs_5_tage": high_5d,
          "max_performance_5_tage": max_perf_5d,
          "candle_time_max_5_tage": candle_time_max,
          "end_kurs_5_tage": close_5d,
          "end_performance_5_tage": end_perf_5d,
      }
    except Exception as e:
      print(f"Fehler bei yfinance Download für {ticker}: {e}")
      return None

  def process_signals_to_journal(self):
    print(
        "Nino verarbeitet aktive Signale (signals -> signals_journal ->"
        " aris_arbeitsspeicher)..."
    )
    try:
      today = datetime.now().date()
      favorite_tickers = self._get_favorite_tickers()

      active_res = (
          self.supabase.table(self.table_active_signals).select("*").execute()
      )
      active_signals = active_res.data or []

      journal_res = (
          self.supabase.table(self.table_signals_journal)
          .select("ticker, candle_time")
          .execute()
      )
      journal_data = journal_res.data or []
      existing_journal_set = {
          (str(j["ticker"]).upper(), str(j["candle_time"])[:10])
          for j in journal_data
          if j and j.get("ticker") and j.get("candle_time")
      }

      for sig in active_signals:
        if not sig:
          continue
        ticker = sig.get("ticker")
        if not ticker or not self.is_valid_ticker(ticker):
          continue

        ticker_upper = ticker.upper()
        sig_date_str = (
            sig.get("candle_time")
            or sig.get("datum")
            or sig.get("signal_datum")
            or sig.get("created_at")
        )
        if not sig_date_str:
          continue

        try:
          sig_date = pd.to_datetime(sig_date_str).date()
          sig_date_iso = sig_date.strftime("%Y-%m-%d")
        except Exception:
          continue

        days_passed = (today - sig_date).days
        # Nur verarbeiten, wenn das Signal mind. 5 Tage alt ist
        if days_passed < 5:
          continue

        if (ticker_upper, sig_date_iso) not in existing_journal_set:
          sig_type = sig.get("signal_type") or sig.get(
              "signal_typ", "Standard"
          )
          sig_price = float(
              sig.get("entry_price")
              or sig.get("preis")
              or sig.get("kurs")
              or 0
          )
          smi_val, adx_val, above_ema = self._parse_meta_data(sig)
          is_fav = ticker_upper in favorite_tickers

          perf_data = self._fetch_5d_performance(
              ticker_upper, sig_date, sig_price
          )
          if not perf_data:
            continue

          journal_entry = {
              "ticker": ticker_upper,
              "candle_time": pd.to_datetime(sig_date_str).isoformat(),
              "signal_typ": sig_type,
              "einstiegspreis_zum_signal": perf_data["base_preis"],
              "smi": smi_val,
              "adx": adx_val,
              "is_favorite": is_fav,
              "above_ema20": above_ema,
              "max_kurs_5_tage": perf_data["max_kurs_5_tage"],
              "max_performance_5_tage": perf_data["max_performance_5_tage"],
              "candle_time_max_5_tage": perf_data["candle_time_max_5_tage"],
              "end_kurs_5_tage": perf_data["end_kurs_5_tage"],
              "end_performance_5_tage": perf_data["end_performance_5_tage"],
              "status": "5D Ausgewertet & Archiviert",
          }

          # 1. Ins signals_journal schreiben
          self.supabase.table(self.table_signals_journal).insert(
              journal_entry
          ).execute()
          existing_journal_set.add((ticker_upper, sig_date_iso))

          # 2. An aris_arbeitsspeicher übergeben
          arbeitsspeicher_entry = journal_entry.copy()
          arbeitsspeicher_entry["quelle"] = "signals_journal"
          self.supabase.table(self.table_aris_arbeitsspeicher).insert(
              arbeitsspeicher_entry
          ).execute()

          # 3. Aus der aktiven 'signals'-Tabelle löschen, damit es aus dem Screener "wandert"
          sig_id = sig.get("id")
          if sig_id:
            self.supabase.table(self.table_active_signals).delete().eq(
                "id", sig_id
            ).execute()

          print(
              f"Signal für {ticker_upper} erfolgreich ausgewertet, ins Journal"
              " verschoben und an aris_arbeitsspeicher übergeben."
          )

    except Exception as e:
      print(f"Fehler in process_signals_to_journal: {e}")

  def process_joris_journal(self):
    print(
        "Nino verarbeitet joris_journal (Berechnung & Übergabe an"
        " aris_arbeitsspeicher)..."
    )
    try:
      today = datetime.now().date()

      joris_res = (
          self.supabase.table(self.table_joris_journal).select("*").execute()
      )
      joris_items = joris_res.data or []

      arb_res = (
          self.supabase.table(self.table_aris_arbeitsspeicher)
          .select("ticker, candle_time")
          .eq("quelle", "joris_journal")
          .execute()
      )
      arb_data = arb_res.data or []
      existing_arb_set = {
          (str(j["ticker"]).upper(), str(j["candle_time"])[:10])
          for j in arb_data
          if j and j.get("ticker") and j.get("candle_time")
      }

      for item in joris_items:
        ticker = item.get("ticker")
        if not ticker or not self.is_valid_ticker(ticker):
          continue

        ticker_upper = ticker.upper()
        date_str = (
            item.get("candle_time")
            or item.get("signal_datum")
            or item.get("created_at")
        )
        if not date_str:
          continue

        try:
          sig_date = pd.to_datetime(date_str).date()
          sig_date_iso = sig_date.strftime("%Y-%m-%d")
        except Exception:
          continue

        days_passed = (today - sig_date).days
        if days_passed < 5:
          continue

        if (ticker_upper, sig_date_iso) in existing_arb_set:
          continue

        base_price = float(
            item.get("preis")
            or item.get("kurs")
            or item.get("einstiegspreis_zum_signal")
            or 0
        )
        perf_data = self._fetch_5d_performance(
            ticker_upper, sig_date, base_price
        )
        if not perf_data:
          continue

        smi_val, adx_val, above_ema = self._parse_meta_data(item)

        updated_joris_data = {
            "max_kurs_5_tage": perf_data["max_kurs_5_tage"],
            "max_performance_5_tage": perf_data["max_performance_5_tage"],
            "candle_time_max_5_tage": perf_data["candle_time_max_5_tage"],
            "end_kurs_5_tage": perf_data["end_kurs_5_tage"],
            "end_performance_5_tage": perf_data["end_performance_5_tage"],
            "status": "5D Ausgewertet",
        }

        item_id = item.get("id")
        if item_id:
          self.supabase.table(self.table_joris_journal).update(
              updated_joris_data
          ).eq("id", item_id).execute()

        arbeitsspeicher_entry = {
            "ticker": ticker_upper,
            "candle_time": pd.to_datetime(date_str).isoformat(),
            "signal_typ": item.get("signal_typ", "Joris"),
            "einstiegspreis_zum_signal": perf_data["base_preis"],
            "smi": smi_val,
            "adx": adx_val,
            "above_ema20": above_ema,
            "max_kurs_5_tage": perf_data["max_kurs_5_tage"],
            "max_performance_5_tage": perf_data["max_performance_5_tage"],
            "candle_time_max_5_tage": perf_data["candle_time_max_5_tage"],
            "end_kurs_5_tage": perf_data["end_kurs_5_tage"],
            "end_performance_5_tage": perf_data["end_performance_5_tage"],
            "quelle": "joris_journal",
            "status": "5D Ausgewertet",
        }

        self.supabase.table(self.table_aris_arbeitsspeicher).insert(
            arbeitsspeicher_entry
        ).execute()
        existing_arb_set.add((ticker_upper, sig_date_iso))
        print(
            f"Joris-Journal Eintrag für {ticker_upper} ausgewertet und an"
            " aris_arbeitsspeicher übergeben."
        )

    except Exception as e:
      print(f"Fehler in process_joris_journal: {e}")

  def run_all(self):
    self.process_signals_to_journal()
    self.process_joris_journal()


if __name__ == "__main__":
  supabase_client = get_db_client()
  nino = NinoSignalsAssistant(supabase_client)
  nino.run_all()