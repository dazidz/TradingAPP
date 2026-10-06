# employees_test/irma.py
import pandas as pd


class IrmaSectorAssistant:
    """Irma – Sektor-Assistenz

    Zuständig für Sektor-Rotation und Berechnung der Signal-Quoten 
    (Anzahl Signale / Gesamt-Ticker im Sektor), mit flexibler Filterung 
    nach Signal-Typ (Alle, Elite, Kauf, etc.).
    """

    def __init__(self, supabase_client):
        self.name = "Irma"
        self.role = "Sektor-Assistenz"
        self.supabase = supabase_client

    def get_top_sector_quotas(self, signal_filter: str = "ALL") -> pd.DataFrame:
        """Ermittelt die Top 10 Sektoren nach prozentualem Signal-Anteil.
        
        signal_filter kann sein:
        - 'ALL': Alle Signale
        - 'ELITE': Nur Elite-Signale
        - 'ELITE_EMA': Nur Elite mit über EMA20
        - 'KAUF': Nur Kauf-Signale
        - 'KAUF_EMA': Nur Kauf mit über EMA20
        (oder exakt der String, der in deiner DB als `signal_type` bzw. in `meta_data` steht)
        """
        if not self.supabase:
            return pd.DataFrame()

        # 1. Watchlist laden (Gesamt-Ticker pro Sektor)
        wl_res = self.supabase.table("watchlist").select("ticker, sector").execute()
        wl_data = wl_res.data if wl_res.data else []
        if not wl_data:
            return pd.DataFrame()

        sector_stats = {}
        for item in wl_data:
            sec = item.get("sector") or "Unbekannt"
            tick = item.get("ticker")
            if not tick:
                continue
            if sec not in sector_stats:
                sector_stats[sec] = set()
            sector_stats[sec].add(tick.upper())

        # 2. Signale dynamisch je nach Filter laden
        query = self.supabase.table("signals").select("ticker, signal_type, meta_data")
        
        sig_res = query.execute()
        sig_data = sig_res.data if sig_res.data else []
        
        filtered_signals = set()
        for item in sig_data:
            t = item.get("ticker")
            if not t:
                continue
            
            s_type = str(item.get("signal_type", "")).strip().lower()
            meta = item.get("meta_data", {})
            # Falls meta_data als String gespeichert ist, ggf. parsen oder direkt prüfen
            if isinstance(meta, str):
                import json
                try:
                    meta = json.loads(meta.replace("'", '"'))
                except:
                    meta = {}
            
            above_ema = meta.get("above_ema20", False)

            # Filterlogik anwenden
            match = False
            if signal_filter == "ALL":
                match = True
            elif signal_filter == "ELITE" and "elite" in s_type:
                match = True
            elif signal_filter == "ELITE_EMA" and "elite" in s_type and above_ema:
                match = True
            elif signal_filter == "KAUF" and ("kauf" in s_type or "buy" in s_type):
                match = True
            elif signal_filter == "KAUF_EMA" and ("kauf" in s_type or "buy" in s_type) and above_ema:
                match = True
            elif s_type == signal_filter.lower():
                # Fallback, falls ein exakter Signal-String übergeben wird
                match = True

            if match:
                filtered_signals.add(t.upper())

        # 3. Quoten berechnen
        rows = []
        for sec, tickers in sector_stats.items():
            total = len(tickers)
            # Sektoren mit nur einem Ticker ausschließen
            if total <= 1:
                continue
            
            signaled = len(tickers.intersection(filtered_signals))
            quota = (signaled / total) * 100 if total > 0 else 0
            
            rows.append({
                "sector": sec,
                "total_tickers": total,
                "signal_tickers": signaled,
                "signal_quota_percent": round(quota, 2)
            })

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        # Absteigend nach Quote sortieren und Top 10 nehmen
        df = df.sort_values(by="signal_quota_percent", ascending=False).head(10)
        return df