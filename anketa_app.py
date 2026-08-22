"""
CAKI Anketa Roditelja — anketa_app.py
JAVNA stranica (BEZ lozinke): agregatni rezultati ankete kvalitete, po
generaciji. Namjerno BEZ raščlambe po predmetu/profesoru — detaljan pregled
je na "Detaljno_interno" stranici, zaštićenoj lozinkom.
"""
import json

import plotly.graph_objects as go
import streamlit as st

from anketa_pipeline import (
    SVI_PREDMETI_GRID,
    _normaliziraj,
    agregat_po_predmetu,
    agregat_po_programu,
    agregat_zadovoljstvo_kombinirano,
    get_gspread_client,
    load_odgovori,
    ucitaj_javnu_vidljivost,
)

st.set_page_config(page_title="CAKI — Statistike ankete", page_icon="📊", layout="centered")

# Paleta — kategorijalni redoslijed iz dataviz smjernica, fiksan (ne dodjeljuje se ponovno pri filtriranju)
BOJE_PROGRAM = {
    "Matematičke gimnazije": "#2a78d6",
    "Opće gimnazije": "#eb6834",
    "Prelog (PSVP)": "#1baf7a",
}
INK_SEKUNDARNI = "#52514e"
GRID_LINIJA = "#e1e0d9"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"


@st.cache_resource
def init_sheet():
    sa_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    gc = get_gspread_client(sa_info)
    return gc.open_by_key(st.secrets["SHEET_ID"])


@st.cache_data(ttl=300)
def dohvati_agregate():
    sheet = init_sheet()
    df = load_odgovori(sheet)
    return df, agregat_po_programu(df), agregat_zadovoljstvo_kombinirano(df)


def _osnovni_layout(fig, **kwargs):
    fig.update_layout(
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE, font=dict(color=INK),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=60, b=40),
        **kwargs,
    )
    return fig


st.title("📊 CAKI anketa roditelja — statistike")
st.caption("Agregatni podaci iz anonimne ankete zadovoljstva, po generaciji upisa u srednju školu.")

df_sirovi, df_programi, df_zadovoljstvo = dohvati_agregate()

if df_programi.empty:
    st.info("Još nema dovoljno odgovora za prikaz statistike.")
    st.stop()

generacije = sorted(df_programi["generacija"].unique())
st.caption(f"Podaci za generacije: {', '.join(str(g) for g in generacije)} — ukupno {len(df_sirovi)} odgovora.")

# --- 1. Trend rezultata na prijemnom, po programu ---
st.subheader("Prosječan rezultat na prijemnom ispitu")
fig = go.Figure()
for program, boja in BOJE_PROGRAM.items():
    podaci = df_programi[df_programi["program"] == program].sort_values("generacija")
    if podaci.empty:
        continue
    fig.add_trace(go.Scatter(
        x=podaci["generacija"], y=podaci["prosjek_prijemni"],
        mode="lines+markers", name=program,
        line=dict(color=boja, width=2), marker=dict(size=8),
    ))
_osnovni_layout(fig, yaxis_title="Bodovi", xaxis_title="Generacija",
                 xaxis=dict(gridcolor=GRID_LINIJA, dtick=1), yaxis=dict(gridcolor=GRID_LINIJA))
st.plotly_chart(fig, use_container_width=True)

# --- 2. Trend prosjeka na simulacijama, po programu ---
st.subheader("Prosječan broj bodova na CAKI simulacijama")
fig2 = go.Figure()
for program, boja in BOJE_PROGRAM.items():
    podaci = df_programi[df_programi["program"] == program].sort_values("generacija")
    if podaci.empty:
        continue
    fig2.add_trace(go.Scatter(
        x=podaci["generacija"], y=podaci["prosjek_simulacije"],
        mode="lines+markers", name=program,
        line=dict(color=boja, width=2), marker=dict(size=8),
    ))
_osnovni_layout(fig2, yaxis_title="Bodovi (prosjek)", xaxis_title="Generacija",
                 xaxis=dict(gridcolor=GRID_LINIJA, dtick=1), yaxis=dict(gridcolor=GRID_LINIJA))
st.plotly_chart(fig2, use_container_width=True)

# --- 3. Simulacije nasuprot stvarnom prijemnom (kalibracija težine testova) ---
st.subheader("Simulacije nasuprot stvarnom prijemnom")
fig3 = go.Figure()
for program, boja in BOJE_PROGRAM.items():
    podaci = df_programi[df_programi["program"] == program]
    if podaci.empty:
        continue
    fig3.add_trace(go.Scatter(
        x=podaci["prosjek_simulacije"], y=podaci["prosjek_prijemni"],
        mode="markers", name=program, marker=dict(size=12, color=boja),
        text=podaci["generacija"],
        hovertemplate="Generacija %{text}<br>Simulacije: %{x:.1f}<br>Prijemni: %{y:.1f}<extra></extra>",
    ))
maks = max(df_programi["prosjek_prijemni"].max(), df_programi["prosjek_simulacije"].max())
fig3.add_trace(go.Scatter(
    x=[0, maks], y=[0, maks], mode="lines",
    line=dict(color=INK_SEKUNDARNI, dash="dot", width=1),
    name="simulacija = prijemni", hoverinfo="skip",
))
_osnovni_layout(fig3, xaxis_title="Prosjek na simulacijama", yaxis_title="Rezultat na prijemnom",
                 xaxis=dict(gridcolor=GRID_LINIJA), yaxis=dict(gridcolor=GRID_LINIJA))
st.plotly_chart(fig3, use_container_width=True)
st.caption("Točkice blizu isprekidane linije znače da su simulacije bile dobra procjena stvarnog rezultata.")

# --- 4. Ukupno zadovoljstvo nastavom (kombinirano, bez raščlambe po predmetu) ---
if not df_zadovoljstvo.empty:
    st.subheader("Ukupno zadovoljstvo nastavom")
    fig4 = go.Figure()
    fig4.add_trace(go.Scatter(
        x=df_zadovoljstvo["generacija"], y=df_zadovoljstvo["prosjecno_zadovoljstvo"],
        mode="lines+markers", line=dict(color=BOJE_PROGRAM["Matematičke gimnazije"], width=2),
        marker=dict(size=8), showlegend=False,
    ))
    _osnovni_layout(fig4, yaxis_title="Prosječna ocjena (1-5)", xaxis_title="Generacija",
                    yaxis=dict(range=[1, 5], gridcolor=GRID_LINIJA), xaxis=dict(gridcolor=GRID_LINIJA, dtick=1))
    st.plotly_chart(fig4, use_container_width=True)
    st.caption(
        "Prosjek svih predmetnih ocjena zajedno (bez raščlambe po predmetu — "
        "to je namjerno, raščlamba po predmetu je de facto raščlamba po profesoru)."
    )

# --- 5. Predmeti koje je admin ručno objavio (prazno dok admin ništa ne objavi) ---
vidljivost = ucitaj_javnu_vidljivost(init_sheet())  # bez cachea — objava mora biti odmah vidljiva
objavljeni_predmeti = [p for p in SVI_PREDMETI_GRID if vidljivost.get(_normaliziraj(p), False)]

if objavljeni_predmeti:
    st.subheader("Rezultati po predmetu")
    st.caption("Ovi predmeti su ručno objavljeni od strane administratora.")
    df_po_predmetu = agregat_po_predmetu(df_sirovi)
    for predmet in objavljeni_predmeti:
        podaci = df_po_predmetu[df_po_predmetu["predmet"] == predmet].sort_values("generacija")
        if podaci.empty:
            continue
        fig5 = go.Figure()
        fig5.add_trace(go.Bar(
            x=podaci["generacija"], y=podaci["prosjek_opce_ocjene"],
            marker_color=BOJE_PROGRAM["Matematičke gimnazije"],
        ))
        _osnovni_layout(fig5, yaxis_title="Prosječna ocjena (1-5)", xaxis_title="Generacija",
                        yaxis=dict(range=[1, 5], gridcolor=GRID_LINIJA), xaxis=dict(gridcolor=GRID_LINIJA, dtick=1))
        st.caption(predmet)
        st.plotly_chart(fig5, use_container_width=True)
