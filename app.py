import gradio as gr
import pandas as pd
from db import get_db_client

def get_signals_df():
    supabase = get_db_client() # <-- HIER FEHLTE DIESE ZEILE
    response = supabase.table("signals").select("*").execute()
    data = response.data
    if not data:
        return pd.DataFrame() 
    return pd.DataFrame(data)


with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🚀 Elite Trading Dashboard")
    
    with gr.Row():
        btn = gr.Button("Signale aktualisieren", variant="primary")
    
    output_table = gr.DataFrame(label="Aktuelle Signale")
    
    # Beim Start einmal laden
    demo.load(fn=get_signals_df, outputs=output_table)
    # Beim Klick aktualisieren
    btn.click(fn=get_signals_df, outputs=output_table)

demo.launch()