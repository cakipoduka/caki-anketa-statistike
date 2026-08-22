"""
CAKI Anketa Roditelja — pages/1_Detaljno_interno.py
INTERNA stranica (lozinka): raščlamba po predmetu (de facto po profesoru),
sve tvrdnje pojedinačno, po generaciji. Isti lozinka-pattern kao ostale
CAKI Streamlit aplikacije (APP_PASSWORD secret, v. app_upisi_admin.py /
caki-evidencija-dolazaka.py).

Broj u imenu datoteke (1_) je Streamlit-ova konvencija za redoslijed u
bočnom izborniku multi-page aplikacije — mora ostati u mapi pages/.
"""
import json

import plotly.graph_objects as go
import streamlit as st

from anketa_pipeline import (
    ROW_LABELS,
    SVI_PREDMETI_GRID,
    _normaliziraj,
    agregat_po_predmetu,
    agregat_tvrdnje_po_predmetu,
    get_gspread_client,
    load_odgovori,
    postavi_javnu_vidljivost,
    ucitaj_javnu_vidljivost,
)

st.set_page_config(page_title="CAKI — Detaljno (interno)", page_icon="🔒", layout="wide")


def provjeri_lozinku() -> bool:
    def na_unos():
        if st.session_state.get("lozinka_unos") == st.secrets.get("APP_PASSWORD"):
            st.session_state["autoriziran"] = True
        else:
            st.session_state["autoriziran"] = False

    if st.session_state.get("autoriziran"):
        return True

    st.title("🔒 CAKI anketa — detaljno (interno)")
    st.text_input("Lozinka", type="password", key="lozinka_unos", on_change=na_unos)
    if st.session_state.get("autoriziran") is False:
        st.error("Pogrešna lozinka.")
    return False


if not provjeri_lozinku():
    st.stop()


@st.cache_resource
def init_sheet():
    sa_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    gc = get_gspread_client(sa_info)
    return gc.open_by_key(st.secrets["SHEET_ID"])


@st.cache_data(ttl=300)
def dohvati_sve():
    sheet = init_sheet()
    df = load_odgovori(sheet)
    return df, agregat_po_predmetu(df)


st.title("🔒 Detaljno — po predmetu (interno)")
st.caption(
    "Ova stranica pokazuje raščlambu po predmetu, što je de facto raščlamba po "
    "profesoru — nije za javni prikaz, samo za interne odluke o nastavi."
)

df_sirovi, df_po_predmetu = dohvati_sve()

if df_po_predmetu.empty:
    st.info("Još nema dovoljno odgovora.")
    st.stop()

predmet = st.selectbox("Predmet", options=SVI_PREDMETI_GRID)

st.subheader(f"Opća ocjena — {predmet}, po generaciji")
podaci_predmet = df_po_predmetu[df_po_predmetu["predmet"] == predmet].sort_values("generacija")
if podaci_predmet.empty:
    st.warning("Nema odgovora za ovaj predmet.")
else:
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=podaci_predmet["generacija"], y=podaci_predmet["prosjek_opce_ocjene"],
        marker_color="#2a78d6", text=podaci_predmet["broj_odgovora"],
        texttemplate="n=%{text}", textposition="outside",
    ))
    fig.update_layout(
        yaxis=dict(range=[1, 5], title="Prosječna ocjena (1-5)"),
        xaxis=dict(title="Generacija", dtick=1),
        plot_bgcolor="#fcfcfb", paper_bgcolor="#fcfcfb", font=dict(color="#0b0b0b"),
        margin=dict(t=40, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

st.subheader(f"Raščlamba po tvrdnji — {predmet}")
df_tvrdnje = agregat_tvrdnje_po_predmetu(df_sirovi, predmet)
if df_tvrdnje.empty:
    st.warning("Nema podataka.")
else:
    tablica = df_tvrdnje.pivot(index="tvrdnja", columns="generacija", values="prosjek").round(2)
    tablica = tablica.reindex(ROW_LABELS)
    st.dataframe(tablica, use_container_width=True)

st.divider()
st.subheader("Javna objava po predmetu")
st.caption(
    "Predmeti označeni 'Objavljeno' pojavljuju se u zasebnom odjeljku na javnoj "
    "stranici (ostatak javne stranice ostaje bez raščlambe po predmetu, kao i do sad)."
)

sheet = init_sheet()
vidljivost = ucitaj_javnu_vidljivost(sheet)  # namjerno bez cachea — promjena mora biti odmah vidljiva

for p in SVI_PREDMETI_GRID:
    trenutno_javno = vidljivost.get(_normaliziraj(p), False)
    stupac_naziv, stupac_gumb = st.columns([3, 1])
    stupac_naziv.write(f"**{p}** — {'🟢 Objavljeno javno' if trenutno_javno else '⚪ Skriveno (samo interno)'}")
    if trenutno_javno:
        if stupac_gumb.button("Ukloni s javnog", key=f"sakrij_{p}"):
            postavi_javnu_vidljivost(sheet, p, False)
            st.rerun()
    else:
        if stupac_gumb.button("Objavi javno", key=f"objavi_{p}"):
            postavi_javnu_vidljivost(sheet, p, True)
            st.rerun()

st.divider()
st.subheader("Sirovi podaci (za izvoz)")
st.dataframe(df_sirovi, use_container_width=True)
st.download_button(
    "⬇️ Preuzmi CSV",
    data=df_sirovi.to_csv(index=False).encode("utf-8"),
    file_name="caki_anketa_svi_odgovori.csv",
    mime="text/csv",
)
