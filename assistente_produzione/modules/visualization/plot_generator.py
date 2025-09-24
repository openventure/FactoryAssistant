# Genera i grafici e tabelle
import streamlit as st
import pandas as pd
import plotly.express as px
import json
import time

st.title("Dashboard Dinamica con Streamlit")

# Loop per aggiornare dinamicamente i dati
placeholder = st.empty()  # Placeholder per aggiornare i dati

while True:
    try:
        # Legge i dati da un file JSON
        with open("data.json", "r") as f:
            data = json.load(f)
        print("I boy!")
        # Converte in DataFrame
        df = pd.DataFrame(data)
        st.subheader("Dati ricevuti")

        # Mostra la tabella
        with placeholder.container():
            st.subheader("Tabella aggiornata")
            st.dataframe(df)

            # Mostra il grafico
            st.subheader("Grafico aggiornato")
            fig = px.bar(df, x="Prodotto", y="Vendite", text_auto=True)
            st.plotly_chart(fig)

        time.sleep(2)  # Aspetta 5 secondi prima di aggiornare
    except Exception as e:
        st.error(f"Errore nel caricamento dei dati: {e}")
        time.sleep(5)