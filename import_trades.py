import streamlit as st
import pandas as pd
from supabase import create_client

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

def import_excel_trades(csv_filename):
    print(f"Lese Datei {csv_filename} ein...")
    
    try:
        df = pd.read_csv(csv_filename, sep=';', engine='python', on_bad_lines='warn')
    except Exception as e:
        print(f"Fehler beim Lesen der CSV: {e}")
        return

    df.columns = df.columns.str.strip().str.lower()

    print(f"Gereinigte Spalten: {df.columns.tolist()}")
    print(f"Anzahl Zeilen im DataFrame: {len(df)}")
    
    # Robustere Bereinigung für deutsche Zahlen, Währungen (EUR/€) und Prozentangaben
    def clean_numeric(series):
        if series is None or series.name not in df.columns:
            return series
        if pd.api.types.is_numeric_dtype(series):
            return series
        
        # Zu Strings machen und Währungssymbole, Leerzeichen sowie Prozentzeichen entfernen
        s_str = series.astype(str).str.replace('€', '', regex=False).str.replace('EUR', '', regex=False).str.replace('%', '', regex=False).str.strip()
        
        # Deutsche Tausenderpunkte entfernen (falls vorhanden) und Komma durch Punkt ersetzen
        # Achtung: Nur Punkte entfernen, die als Tausendertrennzeichen dienen (z.B. 1.234,56 -> 1234,56)
        # Wenn keine Tausenderpunkte da sind, direkt Komma zu Punkt
        s_clean = s_str.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
        return pd.to_numeric(s_clean, errors='coerce')

    for col in ['einstiegskurs', 'ausstiegskurs', 'anzahl', 'gesamtwert', 'g_v', 'performance']:
        if col in df.columns:
            df[col] = clean_numeric(df[col])

    # 1. Einstiegs-Datum & Zeit zusammenführen
    df['einstieg_datum_zeit'] = None
    if 'einstieg_datum' in df.columns:
        zeit_col = df['einstieg_zeit'] if 'einstieg_zeit' in df.columns else '00:00:00'
        valid_in = df['einstieg_datum'].notna() & (df['einstieg_datum'].astype(str).str.strip() != '') & (df['einstieg_datum'].astype(str).str.lower() != 'nan')
        if valid_in.any():
            dt_series = pd.to_datetime(df.loc[valid_in, 'einstieg_datum'].astype(str) + ' ' + zeit_col[valid_in].astype(str), dayfirst=True, errors='coerce')
            df.loc[valid_in, 'einstieg_datum_zeit'] = dt_series.dt.strftime('%Y-%m-%d %H:%M:%S')

    # 2. Ausstiegs-Datum & Zeit zusammenführen
    df['ausstieg_datum_zeit'] = None
    if 'ausstieg_datum' in df.columns:
        zeit_col_out = df['ausstieg_zeit'] if 'ausstieg_zeit' in df.columns else '00:00:00'
        valid_out = df['ausstieg_datum'].notna() & (df['ausstieg_datum'].astype(str).str.strip() != '') & (df['ausstieg_datum'].astype(str).str.lower() != 'nan')
        if valid_out.any():
            dt_series_out = pd.to_datetime(df.loc[valid_out, 'ausstieg_datum'].astype(str) + ' ' + zeit_col_out[valid_out].astype(str), dayfirst=True, errors='coerce')
            df.loc[valid_out, 'ausstieg_datum_zeit'] = dt_series_out.dt.strftime('%Y-%m-%d %H:%M:%S')

    # 3. Gewinn / Verlust (G/V) automatisch berechnen
    if 'g_v' not in df.columns or df['g_v'].isna().all():
        if 'einstiegskurs' in df.columns and 'ausstiegskurs' in df.columns and 'anzahl' in df.columns:
            print("Berechne Gewinn/Verlust (G/V)...")
            g_v_liste = []
            for _, row in df.iterrows():
                e = row.get('einstiegskurs')
                a = row.get('ausstiegskurs')
                qty = row.get('anzahl')
                
                if pd.notna(e) and pd.notna(a) and pd.notna(qty):
                    g_v = (a - e) * qty
                    g_v_liste.append(round(g_v, 2))
                else:
                    g_v_liste.append(None)
            df['g_v'] = g_v_liste

    target_columns = [
        'ticker', 'einstieg_datum_zeit', 'ausstieg_datum_zeit', 
        'anzahl', 'gesamtwert', 'einstiegskurs', 'ausstiegskurs', 
        'signaltype', 'performance', 'g_v', 'notiz'
    ]
    
    existing_cols = [col for col in target_columns if col in df.columns]
    df_import = df[existing_cols]

    records = df_import.to_dict(orient="records")
    
    success_count = 0
    skipped_count = 0
    
    for row in records:
        ticker = row.get('ticker')
        if not ticker or pd.isna(ticker) or str(ticker).lower() == 'nan':
            skipped_count += 1
            continue

        if not row.get('einstieg_datum_zeit'):
            skipped_count += 1
            continue

        clean_row = {k: (None if pd.isna(v) or str(v).lower() == 'nan' else v) for k, v in row.items()}
        
        try:
            supabase.table("trade_journal").insert(clean_row).execute()
            success_count += 1
        except Exception as e:
            print(f"Fehler bei Ticker {ticker}: {e}")
            
    print(f"\nImport abgeschlossen!")
    print(f"- Erfolgreich übertragen: {success_count}")
    print(f"- Übersprungen (leer / ungültig): {skipped_count}")

if __name__ == "__main__":
    import_excel_trades("import_trading_journal.csv")