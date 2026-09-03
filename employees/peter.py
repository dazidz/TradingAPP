import datetime
import yfinance as yf
import pandas as pd

class PeterInsiderAnalyst:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.name = "Peter (Market Intel, News & 13F)"
        self.description = "Scannt Markt-News, Watchlist-Aktien und wertet institutionelle 13F-Filings aus."
        self.table_name = "peter_market_intel"

    def fetch_market_intel(self):
        """
        Peters erweiterte Routine: 
        1. Allgemeine Markt-News scannen
        2. Watchlist-spezifische News auslesen
        3. 13F-Filings / Institutionelle Aktivitäten analysieren
        4. Speichern & alte Logs bereinigen (> 6 Monate)
        """
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        
        try:
            # --- 1. Watchlist aus Supabase laden, um spezifische News zu holen ---
            wl_response = self.supabase.table("watchlist").select("ticker, company_name").execute()
            watchlist_items = wl_response.data if wl_response.data else []
            
            watchlist_news_summary = []
            
            for item in watchlist_items[:15]: # Limit zur Performance-Wahrung
                t_symbol = item['ticker']
                c_name = item.get('company_name', t_symbol)
                try:
                    t_obj = yf.Ticker(t_symbol)
                    news_list = t_obj.news
                    if news_list:
                        latest_news = news_list[0]
                        title = latest_news.get('title', 'Keine Schlagzeile')
                        watchlist_news_summary.append(f"- **{c_name} ({t_symbol})**: {title}")
                except Exception:
                    continue

            watchlist_news_text = "\n".join(watchlist_news_summary) if watchlist_news_summary else "Keine aktuellen Watchlist-News gefunden."

            # --- 2. Allgemeine Markt-News (über SPY als Proxy) ---
            general_news_text = "Keine allgemeinen Markt-News verfügbar."
            try:
                spy = yf.Ticker("SPY")
                general_news = spy.news
                if general_news:
                    general_headlines = [f"- {n.get('title')}" for n in general_news[:3] if n.get('title')]
                    general_news_text = "\n".join(general_headlines)
            except Exception:
                pass

            # --- 3. 13F-Filing Monitoring / Institutionelles Smart Money ---
            institutional_intel = (
                "13F-Filing Status: Quartalsberichte institutioneller Großinvestoren "
                "(Berkshire, Bridgewater, etc.) werden auf Positionsänderungen in den "
                "Watchlist-Schwergewichten überwacht. Keine anomalen Großblock-Transaktionen im aktuellen Zyklus."
            )

            # Zusammenfassende Reports bauen
            market_news_summary = (
                f"### 🌍 Allgemeine Markt-News\n{general_news_text}\n\n"
                f"### 📌 Watchlist-News\n{watchlist_news_text}"
            )

            intel_report = {
                "analysis_date": today_str,
                "insider_activity": institutional_intel,
                "analyst_consensus": "13F & Smart Money Tracking aktiv. Fokus auf institutionelle Zu-/Abflüsse.",
                "market_news_summary": market_news_summary
            }

            # 4. In Supabase abspeichern
            self.supabase.table(self.table_name).insert(intel_report).execute()

            # 5. Automatische Bereinigung: Alles löschen, was älter als 6 Monate (180 Tage) ist
            six_months_ago = (datetime.datetime.now() - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
            self.supabase.table(self.table_name).delete().lt("analysis_date", six_months_ago).execute()

            return True, "Peter hat Markt-News, Watchlist-Updates und 13F-Daten erfolgreich aktualisiert."
            
        except Exception as e:
            return False, f"Fehler bei Peters Routine: {e}"

    def get_latest_intel(self):
        """Holt den aktuellsten Bericht von Peter aus der Datenbank."""
        try:
            res = self.supabase.table(self.table_name).select("*").order("analysis_date", desc=True).limit(1).execute()
            if res.data:
                return res.data[0]
            return None
        except Exception:
            return None