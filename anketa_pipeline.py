"""
CAKI Anketa Roditelja — anketa_pipeline.py
Zajednička logika za čitanje odgovora ankete (Google Forms -> Sheet) i
računanje agregata po programu i po generaciji (školskoj godini).

Isti stack/pattern kao pipeline_upisi.py i baza_zadataka_pipeline.py
(get_gspread_client / Service Account preko gspread-a).
"""
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

# Samo čitanje — ova aplikacija nikad ne piše natrag u Sheet.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# --- Konfiguracija koja odgovara strukturi Forme (v2 upute, CAKI_anketa_upute_priprema.md) ---
# Ako se pitanja u Formi promijene, prilagodi SAMO ove konstante — ostatak koda
# gradi nazive stupaca automatski iz njih. Google Forms izvozi grid pitanje kao
# poseban stupac po retku: "NASLOV GRIDA [tekst retka]".

ROW_LABELS = [
    "Kvalitetnim primjerima i zadacima olakšava razumijevanje gradiva",
    "Jasno i razumljivo izlaže/demonstrira nastavne sadržaje",
    "Ima dobre komunikacijske vještine i stvara ugodnu atmosferu na nastavi",
    "Dostupan/na je i susretljiv/a za konzultacije s učenicima",
    "Koju biste opću ocjenu dali ovom profesoru/profesorici?",
]
OPCA_OCJENA_LABEL = ROW_LABELS[-1]

# program_key -> pitanja vezana uz taj program (kapija + prijemni + simulacije)
PROGRAMI = {
    "mat_gimn": {
        "naziv": "Matematičke gimnazije",
        "pitanje_pohadja": "Je li dijete pohađalo CAKI pripremu za matematičke gimnazije?",
        "pitanje_prijemni": "Vaš rezultat na prijemnom ispitu za matematičke gimnazije (broj bodova)",
        "pitanje_simulacije": "Prosječan broj bodova na simulacijama u CAKI centru za matematičke gimnazije",
        "broj_simulacija": 5,
    },
    "opce_gimn": {
        "naziv": "Opće gimnazije",
        "pitanje_pohadja": "Je li dijete pohađalo CAKI pripremu za opće gimnazije?",
        "pitanje_prijemni": "Vaš rezultat na prijemnom ispitu za opće gimnazije (broj bodova)",
        "pitanje_simulacije": "Prosječan broj bodova na simulacijama u CAKI centru za opće gimnazije",
        "broj_simulacija": 5,
    },
    "prelog": {
        "naziv": "Prelog (PSVP)",
        "pitanje_pohadja": "Je li dijete pohađalo CAKI pripremu za Prelog / PSVP (fizika, kemija, biologija)?",
        "pitanje_prijemni": "Vaš rezultat na prijemnom ispitu za Prelog / PSVP (broj bodova)",
        "pitanje_simulacije": "Prosječan broj bodova na simulacijama u CAKI centru za Prelog / PSVP",
        "broj_simulacija": 3,
    },
}

MATEMATIKA_PITANJE_POHADJA = "Je li dijete pohađalo pripremu iz MATEMATIKE u CAKI centru?"
MATEMATIKA_GRID_NASLOV = "MATEMATIKA"

# Svi predmetni gridovi na jednom mjestu — za "Detaljno" (internu) stranicu.
# Napomena o privatnosti: raščlamba PO PREDMETU je de facto raščlamba PO PROFESORU
# (svaki predmet predaje jedna osoba) — zato ovaj popis hrani samo internu stranicu,
# javna stranica koristi isključivo agregat_zadovoljstvo_kombinirano().
SVI_PREDMETI_GRID = ["HRVATSKI JEZIK", "FIZIKA", "KEMIJA", "BIOLOGIJA", MATEMATIKA_GRID_NASLOV]


def grid_kolona(naslov_grida: str, row_label: str = OPCA_OCJENA_LABEL) -> str:
    """Rekonstruira naziv stupca kako ga Google Forms izvozi za grid pitanje."""
    return f"{naslov_grida} [{row_label}]"


# --- Autentifikacija (identično pipeline_upisi.py / baza_zadataka_pipeline.py) ---

def get_credentials(service_account_info: dict):
    return Credentials.from_service_account_info(service_account_info, scopes=SCOPES)


def get_gspread_client(service_account_info: dict):
    return gspread.authorize(get_credentials(service_account_info))


# --- Učitavanje i priprema podataka ---

def load_odgovori(sheet, worksheet_naziv: str = "CAKI ANKETA pripreme SREDNJA ŠKOLA 26' (Responses)") -> pd.DataFrame:
    """Učitava sirove odgovore i dodaje 'generacija' stupac izveden iz Timestampa.

    Napomena: anketa se provodi svake sezone u istom razdoblju (kraj pripreme/
    upisa), pa je YEAR(Timestamp) dovoljan za razlikovanje generacija. Ako se
    ikad provede anketa koja premošćuje kalendarsku godinu, ovo treba zamijeniti
    pravom "školska godina" logikom (kao trenutna_skolska_godina_broj u CRM §7).
    """
    ws = sheet.worksheet(worksheet_naziv)
    records = ws.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df["generacija"] = df["Timestamp"].dt.year
    return df


def _to_numeric(series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def agregat_po_programu(df: pd.DataFrame) -> pd.DataFrame:
    """Jedan redak po (generacija, program): broj sudionika, prosjek prijemnog, prosjek simulacija."""
    if df.empty:
        return pd.DataFrame()
    redovi = []
    for info in PROGRAMI.values():
        stupac_pohadja = info["pitanje_pohadja"]
        if stupac_pohadja not in df.columns:
            continue
        podaci = df[df[stupac_pohadja].astype(str).str.strip().str.lower() == "da"]
        if podaci.empty:
            continue
        for generacija, grupa in podaci.groupby("generacija"):
            redovi.append({
                "generacija": generacija,
                "program": info["naziv"],
                "broj_sudionika": len(grupa),
                "prosjek_prijemni": _to_numeric(grupa.get(info["pitanje_prijemni"])).mean(),
                "prosjek_simulacije": _to_numeric(grupa.get(info["pitanje_simulacije"])).mean(),
                "broj_simulacija_baza": info["broj_simulacija"],
            })
    return pd.DataFrame(redovi)


def agregat_zadovoljstvo_kombinirano(df: pd.DataFrame) -> pd.DataFrame:
    """JAVNA razina: jedan kombinirani prosjek zadovoljstva po generaciji, preko SVIH
    predmeta zajedno — namjerno bez raščlambe po predmetu (v. napomena o anonimnosti
    profesora u SVI_PREDMETI_GRID)."""
    if df.empty:
        return pd.DataFrame()
    stupci_ocjena = [c for c in (grid_kolona(p) for p in SVI_PREDMETI_GRID) if c in df.columns]
    if not stupci_ocjena:
        return pd.DataFrame()
    dugi = df[["generacija"] + stupci_ocjena].melt(
        id_vars="generacija", value_vars=stupci_ocjena, value_name="ocjena"
    )
    dugi["ocjena"] = _to_numeric(dugi["ocjena"])
    dugi = dugi.dropna(subset=["ocjena"])
    if dugi.empty:
        return pd.DataFrame()
    return dugi.groupby("generacija", as_index=False)["ocjena"].mean().rename(
        columns={"ocjena": "prosjecno_zadovoljstvo"}
    )


def agregat_po_predmetu(df: pd.DataFrame) -> pd.DataFrame:
    """INTERNA razina: prosjek 'opće ocjene' po predmetu po generaciji — de facto po profesoru."""
    if df.empty:
        return pd.DataFrame()
    redovi = []
    for predmet in SVI_PREDMETI_GRID:
        stupac = grid_kolona(predmet)
        if stupac not in df.columns:
            continue
        privremeni = df.assign(_ocjena=_to_numeric(df[stupac])).dropna(subset=["_ocjena"])
        for generacija, grupa in privremeni.groupby("generacija"):
            redovi.append({
                "generacija": generacija,
                "predmet": predmet,
                "prosjek_opce_ocjene": grupa["_ocjena"].mean(),
                "broj_odgovora": len(grupa),
            })
    return pd.DataFrame(redovi)


def agregat_tvrdnje_po_predmetu(df: pd.DataFrame, predmet: str) -> pd.DataFrame:
    """INTERNA razina: prosjek SVAKE tvrdnje (ne samo opće ocjene) za jedan predmet, po generaciji."""
    if df.empty:
        return pd.DataFrame()
    redovi = []
    for row_label in ROW_LABELS:
        stupac = grid_kolona(predmet, row_label)
        if stupac not in df.columns:
            continue
        privremeni = df.assign(_ocjena=_to_numeric(df[stupac])).dropna(subset=["_ocjena"])
        for generacija, grupa in privremeni.groupby("generacija"):
            redovi.append({
                "generacija": generacija,
                "tvrdnja": row_label,
                "prosjek": grupa["_ocjena"].mean(),
                "broj_odgovora": len(grupa),
            })
    return pd.DataFrame(redovi)
