import os
import re
import streamlit as st
import pandas as pd
import numpy as np
from scipy.interpolate import PchipInterpolator
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.colors as pc

# Gestione compatibilità NumPy per l'integrale
trapz_func = getattr(np, 'trapezoid', getattr(np, 'trapz', None))

# Configurazione pagina (barra laterale sempre espansa)
st.set_page_config(
    page_title="ANALISI E CONFRONTO RIGIDEZZA SCARPONI",
    page_icon="🎿",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================================
# CSS CUSTOM: CENTRAGGIO + BLOCCO DEFINITIVO BARRA LATERALE + STILE TABELLE
# =========================================================================
st.markdown("""
    <style>
    /* 1. NASCONDE IL PULSANTE DI CHIUSURA DELLA SIDEBAR */
    [data-testid="stSidebarCollapseButton"],
    [data-testid="collapsedControl"] {
        display: none !important;
    }

    /* 2. Spazio in alto per evitare che il titolo venga sovrapposto */
    .main .block-container {
        max-width: 1200px !important;
        padding-top: 4rem !important;
        padding-bottom: 3rem !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }
    
    /* 3. Centra titoli e testi */
    h1, h2, h3, .stMarkdown p {
        text-align: center !important;
    }
    
    /* 4. Centra il riquadro del Selettore Dataset */
    div[data-testid="stForm"] {
        margin-left: auto !important;
        margin-right: auto !important;
        max-width: 1000px !important;
    }

    /* 5. Centra i messaggi di avviso */
    div[data-testid="stAlert"] {
        text-align: center !important;
        margin-left: auto !important;
        margin-right: auto !important;
        max-width: 1000px !important;
    }

    /* 6. Centra i grafici */
    div[data-testid="stPlotlyChart"], div[data-testid="stpyplot"] {
        display: flex !important;
        justify-content: center !important;
    }

    /* 7. Larghezza fissa e stile Sidebar */
    [data-testid="stSidebar"] {
        min-width: 350px;
        max-width: 380px;
    }
    
    /* 8. Pulsante principale centrato */
    div.stButton > button[kind="primary"] {
        background-color: #ff4b4b;
        color: white;
        font-weight: bold;
        font-size: 18px;
        padding: 12px 28px;
        border-radius: 8px;
        display: block;
        margin: 0 auto;
    }

    /* 9. CENTRAGGIO DEL CONTENUTO E DELLE INTESTAZIONI IN TUTTE LE TABELLE */
    div[data-testid="stDataFrame"] div[role="gridcell"], 
    div[data-testid="stDataFrame"] div[role="columnheader"] {
        justify-content: center !important;
        text-align: center !important;
    }
    table.dataframe td, table.dataframe th {
        text-align: center !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🎿 ANALISI E CONFRONTO RIGIDEZZA SCARPONI")

# PARAMETRI CALCOLO FISICO
PASSO_SECANTE_DEG = 0.25
N_PUNTI_INTERP = 1000
GRADO_TREND_RIGIDEZZA = 3

# Config comune per abilitare zoom con rotellina del mouse su tutti i grafici Plotly
PLOTLY_CONFIG = {
    "scrollZoom": True,
    "displaylogo": False,
    "modeBarButtonsToAdd": ["drawline", "eraseshape"],
}

# =========================================================================
# PARSING INTESTAZIONI E CATALOGAZIONE
# =========================================================================

def estrai_info_header(header_str):
    header_str = str(header_str)
    
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
            
    tok_s = re.search(r'Session\s*(\d+)', header_str, re.IGNORECASE)
    sess = f"Sess.{tok_s.group(1)}" if tok_s else ""
    
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

# Funzione ausiliaria per centrare e formattare le tabelle
def mostra_tabella_centrata(df):
    styler = df.style.set_properties(**{'text-align': 'center'}).set_table_styles([
        {'selector': 'th', 'props': [('text-align', 'center')]}
    ])
    st.dataframe(styler, use_container_width=True)

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
        etichette = [item['label'] for item in catalogo]
        
        with st.form("form_selezione_curve"):
            st.subheader("📋 Selettore Dataset - File, Fogli e Cicli")
            st.write(f"Trovati **{len(etichette)}** cicli validi nei file caricati.")
            
            seleziona_tutte = st.checkbox("✅ Seleziona automaticamente tutte le curve trovate")
            
            default_sel = etichette if seleziona_tutte else []
            
            selezionate = st.multiselect(
                "Scegli manualmente le curve da confrontare:",
                options=etichette,
                default=default_sel,
                placeholder="Clicca qui e scegli i cicli da confrontare..."
            )
            
            st.markdown("---")
            submitted = st.form_submit_button("🚀 Genera Grafici e Confronta", type="primary", use_container_width=True)

        if submitted:
            if not selezionate:
                st.warning("⚠️ Non hai selezionato alcuna curva! Seleziona almeno un ciclo dal menu sopra prima di proseguire.")
            else:
                dati_elaborati = []
                
                with st.spinner("Calcolo della rigidezza e generazione dei grafici in corso..."):
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

                            # Reconstruction of complete hysteresis loop
                            pos_and_full = np.concatenate([pos_andMM, pos_andPP])
                            cop_and_full = np.concatenate([cop_andMM, cop_andPP])
                            pos_rit_full = np.concatenate([pos_ritPP, pos_ritMM])
                            cop_rit_full = np.concatenate([cop_ritPP, cop_ritMM])

                            pos_ciclo = np.concatenate([pos_and_full, pos_rit_full])
                            cop_ciclo = np.concatenate([cop_and_full, cop_rit_full])

                            coppia_max = float(np.max(cop_andPP)) if len(cop_andPP) > 0 else 0.0
                            coppia_min = float(np.min(cop_ciclo)) if len(cop_ciclo) > 0 else 0.0
                            angolo_max = float(np.max(pos_ciclo)) if len(pos_ciclo) > 0 else 0.0
                            angolo_min = float(np.min(pos_ciclo)) if len(pos_ciclo) > 0 else 0.0

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
                                'rig_max_ritMM': rig_max_ritMM,
                                'pos_ciclo': pos_ciclo,
                                'cop_ciclo': cop_ciclo,
                                'coppia_max': coppia_max,
                                'coppia_min': coppia_min,
                                'angolo_max': angolo_max,
                                'angolo_min': angolo_min,
                            })

                if dati_elaborati:
                    palette = pc.qualitative.Plotly + pc.qualitative.D3 + pc.qualitative.Set2
                    colors = [palette[i % len(palette)] for i in range(len(dati_elaborati))]

                    # =====================================================
                    # GRAFICO CICLO DI ISTERESI SOVRAPPOSTO
                    # =====================================================
                    st.subheader("Ciclo di Isteresi")
                    col_plot, col_tab = st.columns([2, 1])

                    with col_plot:
                        fig_ist = go.Figure()
                        for i, d in enumerate(dati_elaborati):
                            fig_ist.add_trace(go.Scatter(
                                x=d['pos_ciclo'], y=d['cop_ciclo'],
                                mode='lines',
                                line=dict(color=colors[i], width=2),
                                name=d['nome_breve'],
                                showlegend=False
                            ))
                        fig_ist.add_hline(y=0, line_color="black", line_width=1.2)
                        fig_ist.add_vline(x=0, line_color="black", line_width=1.2)
                        fig_ist.update_layout(
                            title="Ciclo di Isteresi",
                            xaxis_title="Posizione [°]",
                            yaxis_title="Coppia [Nm]",
                            template="plotly_white",
                            height=520,
                            margin=dict(t=50, b=40, l=50, r=20),
                        )
                        st.plotly_chart(fig_ist, use_container_width=True, config=PLOTLY_CONFIG)

                    with col_tab:
                        st.markdown("**Tabella Coppia e Angoli Max/Min**")
                        df_minmax = pd.DataFrame([{
                            'Dataset': d['nome_breve'],
                            'Coppia Max [Nm]': f"{d['coppia_max']:.2f}",
                            'Coppia Min [Nm]': f"{d['coppia_min']:.2f}",
                            'Angolo Max [°]': f"{d['angolo_max']:.2f}",
                            'Angolo Min [°]': f"{d['angolo_min']:.2f}"
                        } for d in dati_elaborati])
                        
                        # Indice da 1 a N e intestazione 'N°' compatta
                        df_minmax.index = range(1, len(df_minmax) + 1)
                        df_minmax.index.name = "N°"
                        mostra_tabella_centrata(df_minmax)

                        st.markdown("**Legenda**")
                        legenda_html = ""
                        for i, d in enumerate(dati_elaborati):
                            legenda_html += (
                                f"<div style='display:flex; align-items:center; margin-bottom:4px;'>"
                                f"<span style='display:inline-block; width:14px; height:14px; "
                                f"background-color:{colors[i]}; border-radius:3px; margin-right:8px; flex-shrink:0;'></span>"
                                f"<span style='font-size:12.5px;'>{d['nome_breve']}</span>"
                                f"</div>"
                            )
                        st.markdown(legenda_html, unsafe_allow_html=True)

                    st.markdown("---")

                    # =====================================================
                    # GRIGLIA 2x2
                    # =====================================================
                    titles = ['Andata++ (Flex di Spinta)', 'Ritorno++ (Rebound)',
                              'Rigidezza Andata++ (Flex)', 'Rigidezza Ritorno++ (Rebound)']

                    fig = make_subplots(
                        rows=2, cols=2,
                        subplot_titles=titles,
                        vertical_spacing=0.12,
                        horizontal_spacing=0.08
                    )

                    for i, d in enumerate(dati_elaborati):
                        c = colors[i]
                        show_legend = True

                        # Coppia vs Posizione - Andata++
                        fig.add_trace(go.Scatter(
                            x=d['pos_andPP'], y=d['cop_andPP'],
                            mode='lines', line=dict(color=c, width=1.8),
                            name=f"{d['nome_breve']} ({d['lav_andPP']:.2f} J)",
                            legendgroup=d['nome_breve'], showlegend=show_legend
                        ), row=1, col=1)

                        # Coppia vs Posizione - Ritorno++
                        fig.add_trace(go.Scatter(
                            x=d['pos_ritPP'], y=d['cop_ritPP'],
                            mode='lines', line=dict(color=c, width=1.8),
                            name=f"{d['nome_breve']} ({d['lav_ritPP']:.2f} J)",
                            legendgroup=d['nome_breve'], showlegend=False
                        ), row=1, col=2)

                        # Rigidezza Andata++
                        fig.add_trace(go.Scatter(
                            x=d['th_andPP'], y=d['rig_andPP'],
                            mode='lines', line=dict(color=c, width=1, dash='dash'),
                            opacity=0.4, name=d['nome_breve'],
                            legendgroup=d['nome_breve'], showlegend=False
                        ), row=2, col=1)
                        fig.add_trace(go.Scatter(
                            x=d['th_andPP'], y=d['trend_andPP'],
                            mode='lines', line=dict(color=c, width=2.5),
                            name=d['nome_breve'],
                            legendgroup=d['nome_breve'], showlegend=False
                        ), row=2, col=1)

                        # Rigidezza Ritorno++
                        fig.add_trace(go.Scatter(
                            x=d['th_ritPP'], y=d['rig_ritPP'],
                            mode='lines', line=dict(color=c, width=1, dash='dash'),
                            opacity=0.4, name=d['nome_breve'],
                            legendgroup=d['nome_breve'], showlegend=False
                        ), row=2, col=2)
                        fig.add_trace(go.Scatter(
                            x=d['th_ritPP'], y=d['trend_ritPP'],
                            mode='lines', line=dict(color=c, width=2.5),
                            name=d['nome_breve'],
                            legendgroup=d['nome_breve'], showlegend=False
                        ), row=2, col=2)

                    fig.update_xaxes(title_text="Posizione [°]", row=1, col=1)
                    fig.update_xaxes(title_text="Posizione [°]", row=1, col=2)
                    fig.update_xaxes(title_text="Posizione [°]", row=2, col=1)
                    fig.update_xaxes(title_text="Posizione [°]", row=2, col=2)
                    fig.update_yaxes(title_text="Coppia [Nm]", row=1, col=1)
                    fig.update_yaxes(title_text="Coppia [Nm]", row=1, col=2)
                    fig.update_yaxes(title_text="Rigidezza [Nm/°]", row=2, col=1)
                    fig.update_yaxes(title_text="Rigidezza [Nm/°]", row=2, col=2)

                    # Unificazione assi Y
                    y_cop_all = np.concatenate([d['cop_andPP'] for d in dati_elaborati] + [d['cop_ritPP'] for d in dati_elaborati])
                    y_rig_all = np.concatenate([d['rig_andPP'] for d in dati_elaborati] + [d['rig_ritPP'] for d in dati_elaborati])
                    if len(y_cop_all) > 0:
                        pad_cop = 0.05 * (y_cop_all.max() - y_cop_all.min() + 1e-9)
                        fig.update_yaxes(range=[y_cop_all.min() - pad_cop, y_cop_all.max() + pad_cop], row=1, col=1)
                        fig.update_yaxes(range=[y_cop_all.min() - pad_cop, y_cop_all.max() + pad_cop], row=1, col=2)
                    if len(y_rig_all) > 0:
                        pad_rig = 0.05 * (y_rig_all.max() - y_rig_all.min() + 1e-9)
                        fig.update_yaxes(range=[y_rig_all.min() - pad_rig, y_rig_all.max() + pad_rig], row=2, col=1)
                        fig.update_yaxes(range=[y_rig_all.min() - pad_rig, y_rig_all.max() + pad_rig], row=2, col=2)

                    fig.update_layout(
                        template="plotly_white",
                        height=850,
                        legend=dict(
                            orientation="h",
                            font=dict(size=9),
                            yanchor="bottom",
                            y=1.06,
                            xanchor="center",
                            x=0.5,
                        ),
                        margin=dict(t=140, b=40, l=50, r=20),
                    )
                    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

                    # =====================================================
                    # TABELLA RIASSUNTIVA PRESTAZIONI
                    # =====================================================
                    st.subheader("📊 Riepilogo Numerico Prestazioni")
                    
                    df_riepilogo = pd.DataFrame([{
                        'Dataset / Prova': d['nome_breve'],
                        'Energia spesa in flex di spinta [J]': f"{d['lav_andPP']:.2f}",
                        'Energia Dissipata [J]': f"{d['e_dissipata']:.2f}",
                        'Energia spesa in tenuta post. [J]': f"{d['lav_ritMM']:.2f}",
                        'Tenuta Max Post. [Nm/°]': f"{d['rig_max_ritMM']:.2f}"
                    } for d in dati_elaborati])
                    
                    # Indice da 1 a N e intestazione 'N°' compatta
                    df_riepilogo.index = range(1, len(df_riepilogo) + 1)
                    df_riepilogo.index.name = "N°"
                    
                    mostra_tabella_centrata(df_riepilogo)

else:
    st.info("👈 Carica uno o più file Excel dal menu a sinistra per iniziare la scansione dei dati.")
