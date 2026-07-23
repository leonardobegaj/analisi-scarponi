import os
import re
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import PchipInterpolator

# Gestione compatibilità NumPy per l'integrale
trapz_func = getattr(np, 'trapezoid', getattr(np, 'trapz', None))

# Configurazione pagina a larghezza intera
st.set_page_config(
    page_title="Confronto Rigidezza & Isteresi Scarponi",
    page_icon="🎿",
    layout="wide"
)

# CSS Custom per allargare la sidebar e migliorare la visibilità del selettore
st.markdown("""
    <style>
    [data-testid="stSidebar"] {
        min-width: 350px;
        max-width: 380px;
    }
    .stMultiSelect div[data-baseweb="select"] span {
        white-space: normal !important;
        word-break: break-word !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🎿 Confronto Meccanico Rigidezza e Isteresi")

# PARAMETRI CALCOLO FISICO (uguali allo script MATLAB)
PASSO_SECANTE_DEG = 0.25
N_PUNTI_INTERP = 1000
GRADO_TREND_RIGIDEZZA = 3

# =========================================================================
# PARSING INTESTAZIONI E CATALOGAZIONE (IDENTICO A MATLAB)
# =========================================================================

def estrai_info_header(header_str):
    header_str = str(header_str)
    
    # 1. Identificazione Prova (es. paris_1, paris_2)
    tok_paris = re.search(r'(paris_\d+)', header_str, re.IGNORECASE)
    if tok_paris:
        prova = tok_paris.group(1)
    else:
        tok_dash = re.search(r'-\s*([A-Za-z0-9_]+)', header_str)
        if tok_dash and tok_dash.group(1).lower() not in ['altro', 'posizione', 'coppia']:
            prova = tok_dash.group(1)
        else:
            parole = re.findall(r'[A-Za-z0-9_]+', header_str)
            escludi = {'altro', 'posizione', 'coppia', 'n', 'm', 'deg', 'session', 'saves', 'cycle', 'unnamed'}
            valide = [w for w in parole if w.lower() not in escludi]
            prova = valide[0] if valide else 'Prova'
            
    # 2. Identificazione Sessione (es. Session 1 -> Sess.1)
    tok_s = re.search(r'Session\s*(\d+)', header_str, re.IGNORECASE)
    sess = f"Sess.{tok_s.group(1)}" if tok_s else ""
    
    # 3. Identificazione Ciclo (es. Cycle 1 -> Cycle1)
    tok_c = re.search(r'(Cycle\s*\d+)', header_str, re.IGNORECASE)
    ciclo = tok_c.group(1).replace(" ", "") if tok_c else ""
    
    dati_str = " ".join(filter(None, [prova, sess, ciclo])).strip()
    return dati_str if dati_str else header_str

def costruisci_catalogo(uploaded_files):
    catalogo = []
    pos_kw = ['posiz', 'theta', 'deg', 'angle', 'posizione', '°']
    tor_kw = ['coppia', 'torque', 'tau', 'nm', 'nmm', 'cycle', 'altro']
    
    for file in uploaded_files:
        file_no_ext = os.path.splitext(file.name)[0]
        try:
            xls = pd.ExcelFile(file)
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet_name)
                num_cols = len(df.columns)
                if num_cols < 2:
                    continue
                
                col_names = list(df.columns)
                coppie_trovate = False
                
                # --- METODO 1: Riconoscimento Parole Chiave ---
                c = 0
                while c < num_cols:
                    col_name = str(col_names[c])
                    low_name = col_name.lower()
                    
                    is_pos = sum(1 for k in pos_kw if k in low_name) > sum(1 for k in tor_kw if k in low_name)
                    if is_pos:
                        c_cop = -1
                        if c < num_cols - 1:
                            low_next = str(col_names[c+1]).lower()
                            if sum(1 for k in tor_kw if k in low_next) > 0:
                                c_cop = c + 1
                        if c_cop == -1 and c > 0:
                            low_prev = str(col_names[c-1]).lower()
                            if sum(1 for k in tor_kw if k in low_prev) > 0:
                                c_cop = c - 1
                                
                        if c_cop != -1:
                            pos_col_name = col_name
                            cop_col_name = str(col_names[c_cop])
                            
                            dati_str = estrai_info_header(cop_col_name)
                            label = f"[FILE: {file_no_ext}] [FOGLIO: {sheet_name}] --> {dati_str}"
                            nome_breve = f"{dati_str} ({file_no_ext} - {sheet_name})"
                            
                            if not any(x['file_name'] == file.name and x['sheet'] == sheet_name and x['cop_col'] == cop_col_name for x in catalogo):
                                catalogo.append({
                                    'file_name': file.name,
                                    'sheet': sheet_name,
                                    'pos_col': pos_col_name,
                                    'cop_col': cop_col_name,
                                    'label': label,
                                    'nome_breve': nome_breve,
                                    'df': df
                                })
                                coppie_trovate = True
                    c += 1
                    
                # --- METODO 2 (FALLBACK): Colonne numeriche adiacenti ---
                if not coppie_trovate:
                    c = 0
                    while c < num_cols - 1:
                        v1 = pd.to_numeric(df.iloc[:, c], errors='coerce').dropna().values
                        v2 = pd.to_numeric(df.iloc[:, c+1], errors='coerce').dropna().values
                        
                        if len(v1) >= 5 and len(v2) >= 5:
                            pos_col_name = str(col_names[c])
                            cop_col_name = str(col_names[c+1])
                            
                            nome_prova = pos_col_name if not pos_col_name.startswith('Unnamed') else f"Prova_Col_{c+1}"
                            label = f"[FILE: {file_no_ext}] [FOGLIO: {sheet_name}] --> {nome_prova}"
                            nome_breve = f"{nome_prova} ({file_no_ext} - {sheet_name})"
                            
                            if not any(x['file_name'] == file.name and x['sheet'] == sheet_name and x['cop_col'] == cop_col_name for x in catalogo):
                                catalogo.append({
                                    'file_name': file.name,
                                    'sheet': sheet_name,
                                    'pos_col': pos_col_name,
                                    'cop_col': cop_col_name,
                                    'label': label,
                                    'nome_breve': nome_breve,
                                    'df': df
                                })
                            c += 2
                        else:
                            c += 1
        except Exception as e:
            st.warning(f"Errore nella lettura del file {file.name}: {e}")
    return catalogo

# =========================================================================
# FUNZIONI DI CALCOLO FISICO
# =========================================================================

def to_double_vector(series):
    return pd.to_numeric(series, errors='coerce').values

def separa_andata_ritorno(pos, cop):
    if len(pos) < 5:
        return np.array([]), np.array([]), np.array([]), np.array([])
    idx_max = np.argmax(pos)
    idx_min = np.argmin(pos)
    if idx_max == idx_min:
        return np.array([]), np.array([]), np.array([]), np.array([])
    
    if idx_max < idx_min:
        pos_rit, cop_rit = pos[idx_max:idx_min+1], cop[idx_max:idx_min+1]
        pos_and = np.concatenate([pos[idx_min:], pos[:idx_max+1]])
        cop_and = np.concatenate([cop[idx_min:], cop[:idx_max+1]])
    else:
        pos_and, cop_and = pos[idx_min:idx_max+1], cop[idx_min:idx_max+1]
        pos_rit = np.concatenate([pos[idx_max:], pos[:idx_min+1]])
        cop_rit = np.concatenate([cop[idx_max:], cop[:idx_min+1]])
        
    return pos_and, cop_and, pos_rit, cop_rit

def azzera_coppia(pos_and, cop_and, cop_rit):
    if len(pos_and) < 2:
        return cop_and, cop_rit, 0.0
    sort_idx = np.argsort(pos_and)
    p_s, c_s = pos_and[sort_idx], cop_and[sort_idx]
    u_p, u_idx = np.unique(p_s, return_index=True)
    u_c = c_s[u_idx]
    
    if len(u_p) > 1 and u_p.min() <= 0 <= u_p.max():
        offset = float(np.interp(0, u_p, u_c))
    else:
        offset = 0.0
    return cop_and - offset, cop_rit - offset, offset

def calcola_rigidezza_secante(theta_deg, coppia, passo_secante=0.25, margine_taglio=0.3):
    if len(theta_deg) < 2:
        return np.zeros_like(theta_deg)
    
    sort_idx = np.argsort(theta_deg)
    t_s, c_s = theta_deg[sort_idx], coppia[sort_idx]
    u_t, u_idx = np.unique(t_s, return_index=True)
    u_c = c_s[u_idx]
    
    if len(u_t) < 2:
        return np.zeros_like(theta_deg)
        
    t_min = u_t[0]
    t_max = max(u_t[-1] - margine_taglio, u_t[0])
    n_intervalli = max(int(np.round((t_max - t_min) / passo_secante)), 1)
    
    t_nodi = np.linspace(t_min, t_max, n_intervalli + 1)
    
    try:
        pchip = PchipInterpolator(u_t, u_c)
        c_nodi = pchip(t_nodi)
    except Exception:
        c_nodi = np.interp(t_nodi, u_t, u_c)
        
    t_secante = (t_nodi[:-1] + t_nodi[1:]) / 2.0
    dt = np.diff(t_nodi)
    dt[dt == 0] = 1e-6
    rig_secante = np.diff(c_nodi) / dt
    
    if len(t_secante) >= 2:
        rig_sorted = np.interp(t_s, t_secante, rig_secante, left=rig_secante[0], right=rig_secante[-1])
    else:
        rig_sorted = np.full_like(t_s, rig_secante[0] if len(rig_secante) > 0 else 0)
        
    rigidezza = np.zeros_like(theta_deg)
    rigidezza[sort_idx] = rig_sorted
    return rigidezza

def funz_calcola_rigidezza(posizione_deg, coppia, passo_secante=0.25, n_punti=1000):
    if len(posizione_deg) < 2:
        return np.array([]), np.array([]), np.array([]), 0.0
    
    df_temp = pd.DataFrame({'pos': posizione_deg, 'cop': coppia}).groupby('pos').mean().reset_index()
    pos_u = df_temp['pos'].values
    cop_u = df_temp['cop'].values
    
    if len(pos_u) < 2:
        return np.array([]), np.array([]), np.array([]), 0.0
        
    theta_deg = np.linspace(pos_u.min(), pos_u.max(), n_punti)
    
    try:
        pchip = PchipInterpolator(pos_u, cop_u)
        coppia_interp = pchip(theta_deg)
    except Exception:
        coppia_interp = np.interp(theta_deg, pos_u, cop_u)
        
    rigidezza = calcola_rigidezza_secante(theta_deg, coppia_interp, passo_secante)
    theta_rad = np.radians(theta_deg)
    lavoro = float(np.abs(trapz_func(coppia_interp, theta_rad)))
    
    return theta_deg, coppia_interp, rigidezza, lavoro

def fit_trend_polinomiale(x, y, grado=3):
    if len(x) < (grado + 1):
        return np.zeros_like(x)
    try:
        p = np.polyfit(x, y, grado)
        return np.polyval(p, x)
    except Exception:
        return np.zeros_like(x)

# =========================================================================
# FLUSSO DELL'INTERFACCIA UTENTE
# =========================================================================

st.sidebar.header("1. Caricamento File")
uploaded_files = st.sidebar.file_uploader(
    "Seleziona uno o più file Excel", 
    type=["xlsx", "xls", "xlsm"], 
    accept_multiple_files=True
)

if uploaded_files:
    catalogo = costruisci_catalogo(uploaded_files)
    
    if not catalogo:
        st.error("Nessuna colonna valida di Posizione/Coppia trovata nei file caricati.")
    else:
        st.markdown("---")
        st.subheader("📋 Selettore Dataset - File, Fogli e Cicli")
        st.caption("Seleziona le curve da confrontare dal catalogo scansionato:")
        
        etichette = [item['label'] for item in catalogo]
        
        # Gestione stato selezione
        if 'selected_curves' not in st.session_state:
            st.session_state.selected_curves = []
            
        col_b1, col_b2, _ = st.columns([1.5, 1.5, 7])
        if col_b1.button("✅ Seleziona Tutti"):
            st.session_state.selected_curves = etichette
            st.rerun()
        if col_b2.button("❌ Deseleziona Tutti"):
            st.session_state.selected_curves = []
            st.rerun()
            
        selezionate = st.multiselect(
            "Curve disponibili:",
            options=etichette,
            default=st.session_state.selected_curves,
            placeholder="Clicca qui per selezionare le curve da visualizzare..."
        )
        
        st.session_state.selected_curves = selezionate
        
        if not selezionate:
            st.info("👆 Seleziona almeno una curva dall'elenco qui sopra per visualizzare i grafici e la tabella dei dati.")
        else:
            dati_elaborati = []
            
            for item in catalogo:
                if item['label'] in selezionate:
                    df = item['df']
                    pos_raw = to_double_vector(df[item['pos_col']])
                    cop_raw = to_double_vector(df[item['cop_col']])
                    
                    valid = ~np.isnan(pos_raw) & ~np.isnan(cop_raw)
                    pos, cop = pos_raw[valid], cop_raw[valid]
                    
                    if len(pos) < 5:
                        continue
                        
                    pos_and, cop_and, pos_rit, cop_rit = separa_andata_ritorno(pos, cop)
                    
                    # Segmentazione Positivi (PP) e Negativi (MM)
                    idx_andPP = pos_and >= 0
                    idx_andMM = pos_and <= 0
                    idx_ritPP = pos_rit >= 0
                    idx_ritMM = pos_rit <= 0
                    
                    pos_andPP, cop_andPP = pos_and[idx_andPP], cop_and[idx_andPP]
                    pos_andMM, cop_andMM = pos_and[idx_andMM], cop_and[idx_andMM]
                    pos_ritPP, cop_ritPP = pos_rit[idx_ritPP], cop_rit[idx_ritPP]
                    pos_ritMM, cop_ritMM = pos_rit[idx_ritMM], cop_rit[idx_ritMM]
                    
                    cop_andPP, cop_ritPP, _ = azzera_coppia(pos_andPP, cop_andPP, cop_ritPP)
                    cop_andMM, cop_ritMM, _ = azzera_coppia(pos_andMM, cop_andMM, cop_ritMM)
                    
                    th_andPP, _, rig_andPP, lav_andPP = funz_calcola_rigidezza(pos_andPP, cop_andPP, PASSO_SECANTE_DEG, N_PUNTI_INTERP)
                    th_ritPP, _, rig_ritPP, lav_ritPP = funz_calcola_rigidezza(pos_ritPP, cop_ritPP, PASSO_SECANTE_DEG, N_PUNTI_INTERP)
                    th_ritMM, _, rig_ritMM, lav_ritMM = funz_calcola_rigidezza(pos_ritMM, cop_ritMM, PASSO_SECANTE_DEG, N_PUNTI_INTERP)
                    
                    e_dissipata = lav_andPP - lav_ritPP
                    rig_max_ritMM = float(np.max(rig_ritMM)) if len(rig_ritMM) > 0 else 0.0
                    
                    trend_andPP = fit_trend_polinomiale(th_andPP, rig_andPP, GRADO_TREND_RIGIDEZZA)
                    trend_ritPP = fit_trend_polinomiale(th_ritPP, rig_ritPP, GRADO_TREND_RIGIDEZZA)
                    
                    dati_elaborati.append({
                        'nome_breve': item['nome_breve'],
                        'pos_andPP': pos_andPP, 'cop_andPP': cop_andPP,
                        'pos_ritPP': pos_ritPP, 'cop_ritPP': cop_ritPP,
                        'th_andPP': th_andPP, 'rig_andPP': rig_andPP, 'trend_andPP': trend_andPP,
                        'th_ritPP': th_ritPP, 'rig_ritPP': rig_ritPP, 'trend_ritPP': trend_ritPP,
                        'lav_andPP': lav_andPP,
                        'lav_ritPP': lav_ritPP,
                        'e_dissipata': e_dissipata,
                        'lav_ritMM': lav_ritMM,
                        'rig_max_ritMM': rig_max_ritMM
                    })

            if dati_elaborati:
                st.markdown("---")
                # =========================================================
                # GRAFICI (Griglia 2x2 come su MATLAB)
                # =========================================================
                fig, axs = plt.subplots(2, 2, figsize=(14, 9))
                colors = plt.cm.tab10(np.linspace(0, 1, len(dati_elaborati)))

                for i, d in enumerate(dati_elaborati):
                    c = colors[i]
                    # Subplot 1: Andata++
                    axs[0, 0].plot(d['pos_andPP'], d['cop_andPP'], color=c, label=f"{d['nome_breve']} ({d['lav_andPP']:.2f} J)")
                    # Subplot 2: Ritorno++
                    axs[0, 1].plot(d['pos_ritPP'], d['cop_ritPP'], color=c, label=f"{d['nome_breve']} ({d['lav_ritPP']:.2f} J)")
                    # Subplot 3: Rigidezza Andata++
                    axs[1, 0].plot(d['th_andPP'], d['rig_andPP'], '--', color=c, alpha=0.4)
                    axs[1, 0].plot(d['th_andPP'], d['trend_andPP'], '-', color=c, label=d['nome_breve'], linewidth=2)
                    # Subplot 4: Rigidezza Ritorno++
                    axs[1, 1].plot(d['th_ritPP'], d['rig_ritPP'], '--', color=c, alpha=0.4)
                    axs[1, 1].plot(d['th_ritPP'], d['trend_ritPP'], '-', color=c, label=d['nome_breve'], linewidth=2)

                titles = ['Andata++ (Flex di Spinta)', 'Ritorno++ (Rebound)', 'Rigidezza Andata++ (Flex)', 'Rigidezza Ritorno++ (Rebound)']
                x_labels = ['Posizione [°]', 'Posizione [°]', 'Posizione [°]', 'Posizione [°]']
                y_labels = ['Coppia [Nm]', 'Coppia [Nm]', 'Rigidezza [Nm/°]', 'Rigidezza [Nm/°]']

                for idx, ax in enumerate(axs.flat):
                    ax.set_title(titles[idx], fontweight='bold')
                    ax.set_xlabel(x_labels[idx])
                    ax.set_ylabel(y_labels[idx])
                    ax.grid(True, linestyle=':', alpha=0.6)
                    ax.legend(fontsize=8)

                plt.tight_layout()
                st.pyplot(fig)

                # =========================================================
                # TABELLA RIASSUNTIVA PRESTAZIONI (uitable)
                # =========================================================
                st.subheader("📊 Riepilogo Numerico Prestazioni")
                
                df_riepilogo = pd.DataFrame([{
                    'Dataset / Prova': d['nome_breve'],
                    'Energia spesa [J]': f"{d['lav_andPP']:.2f}",
                    'Dissipata [J]': f"{d['e_dissipata']:.2f}",
                    'Tenuta Post. [J]': f"{d['lav_ritMM']:.2f}",
                    'Rig. Max Post. [Nm/°]': f"{d['rig_max_ritMM']:.2f}"
                } for d in dati_elaborati])
                
                st.dataframe(df_riepilogo, use_container_width=True)

else:
    st.info("👈 Carica uno o più file Excel dal menu a sinistra per iniziare la scansione dei dati.")
