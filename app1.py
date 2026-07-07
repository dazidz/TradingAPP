import streamlit as st
from supabase import create_client
import os

# Verbindung zu Supabase
URL = "https://pyyyrbhxqpsngslazzpq.supabase.co/"
KEY = "sb_publishable_aHdbyoX1tnJZStUvry2w5A_jrTeA1jC"
supabase = create_client(url, key)

st.title("Ticker-Screener Dashboard")

# Daten laden
response = supabase.table("signals").select("*").execute()
st.dataframe(response.data)