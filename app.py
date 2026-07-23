import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

st.set_page_config(
    page_title="Analizzatore Isteresi Scarponi",
    page_icon="🎿",
    layout="wide"
)

st.title("🎿 Analizzatore Isteresi Scarponi da Sci")
st.write("Carica un file Excel o CSV per calcolare l'energia dissipata e la rigidezza.")

st.sidebar.header("Caricamento Dati")
uploaded_file = st.sidebar.file_uploader("Scegli un file Excel o CSV", type=["xlsx", "csv"])

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        df.columns = [str(c).lower().strip() for c in df.columns]
        
        x_col = next((c for c in df.columns if 'ang' in c or 'pos' in c or 'angle' in c), df.columns[0])
        y_col = next((c for c in df.columns if 'cop' in c or 'tor' in c or 'for' in c), df.columns[1])
        
        x = df[x_col].values
        y = df[y_col].values
        
        peak_idx = np.argmax(x)
        
        x_andata, y_andata = x[:peak_idx+1], y[:peak_idx+1]
        x_ritorno, y_ritorno = x[peak_idx:], y[peak_idx:]
        
        is_degree = np.max(np.abs(x)) > 1.5
        x_rad_andata = np.radians(x_andata) if is_degree else x_andata
        x_rad_ritorno = np.radians(x_ritorno) if is_degree else x_ritorno
        
        w_andata = np.trapz(y_andata, x_rad_andata)
        w_ritorno = np.abs(np.trapz(y_ritorno, x_rad_ritorno))
        
        efficienza = (w_ritorno / w_andata) * 100 if w_andata > 0 else 0
        dissipata = 100 - efficienza
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Lavoro Andata", f"{w_andata:.2f} J")
        col2.metric("Lavoro Ritorno", f"{w_ritorno:.2f} J")
        col3.metric("Efficienza Elastica", f"{efficienza:.1f} %")
        col4.metric("Energia Dissipata", f"{dissipata:.1f} %")
        
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.plot(x_andata, y_andata, label='Andata (Carico)', color='#1e3d59', linewidth=2.5)
        ax.plot(x_ritorno, y_ritorno, label='Ritorno (Scarico)', color='#ff6e40', linewidth=2.5, linestyle='--')
        
        ax.fill_between(x_andata, y_andata, np.interp(x_andata, x_ritorno[::-1], y_ritorno[::-1]), 
                        color='#1e3d59', alpha=0.1, label='Energia Dissipata')
        
        ax.set_xlabel(f"Angolo ({'°' if is_degree else 'rad'})")
        ax.set_ylabel("Coppia (Nm)")
        ax.set_title("Ciclo di Isteresi Meccanica")
        ax.grid(True, linestyle=':', alpha=0.6)
        ax.legend()
        
        st.pyplot(fig)
        
    except Exception as e:
        st.error(f"Errore durante l'elaborazione del file: {e}")
else:
    st.info("👈 Carica un file dal menu a sinistra per vedere i grafici.")
