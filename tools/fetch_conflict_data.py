import io
import csv
import zipfile
import requests
from ibm_watsonx_orchestrate.agent_builder.tools import tool

# GDELT v2 Events CSV column indices (confirmed from live data)
COL_EVENT_ROOT = 28   # EventRootCode  (18=Assault, 19=Fight, 20=ConvForce)
COL_EVENT_CODE = 26   # Full EventCode
COL_GOLDSTEIN  = 30   # GoldsteinScale (-10 worst .. +10 best)
COL_MENTIONS   = 31   # NumMentions
COL_ACTION_NAME= 52   # ActionGeo_FullName
COL_ACTION_CC  = 53   # ActionGeo_CountryCode
COL_ACTION_LAT = 56   # ActionGeo_Lat
COL_ACTION_LON = 57   # ActionGeo_Long
COL_SOURCE_URL = 60   # SOURCEURL
COL_SQLDATE    = 1    # Day (YYYYMMDD)

# CAMEO root codes for violent conflict
CONFLICT_ROOTS = {'18', '19', '20'}

# FIPS → country name mapping for the most common conflict zones
CC_MAP = {
    'IS': 'Israel', 'PS': 'Palestina', 'RS': 'Rússia', 'UP': 'Ucrânia',
    'UA': 'Ucrânia', 'SU': 'Sudão', 'BM': 'Myanmar', 'YM': 'Iêmen',
    'HA': 'Haiti',   'CG': 'Congo (RDC)', 'IR': 'Irã', 'LE': 'Líbano',
    'SY': 'Síria',   'ET': 'Etiópia', 'LY': 'Líbia', 'ML': 'Mali',
    'SO': 'Somália', 'MZ': 'Moçambique', 'AF': 'Afeganistão',
    'IZ': 'Iraque',  'SA': 'Arábia Saudita', 'PK': 'Paquistão',
}

# Hardcoded fallback: major known active conflicts that MUST appear
# Used when they don't appear in the GDELT 15-min window
FALLBACK_CONFLICTS = [
    {"id": "fallback-gaza",    "title": "Conflito armado ativo — Gaza/Israel",         "country": "Palestina", "lat": 31.35, "lon": 34.30, "severity": 5},
    {"id": "fallback-ukraine", "title": "Guerra Rússia-Ucrânia — frente leste",        "country": "Ucrânia",  "lat": 48.50, "lon": 37.50, "severity": 5},
    {"id": "fallback-sudan",   "title": "Guerra civil ativa — Sudão (RSF vs Exército)", "country": "Sudão",   "lat": 15.55, "lon": 32.53, "severity": 5},
    {"id": "fallback-myanmar", "title": "Conflito armado — Myanmar (junta vs grupos)",  "country": "Myanmar",  "lat": 21.00, "lon": 96.00, "severity": 4},
    {"id": "fallback-yemen",   "title": "Guerra civil e ataques Houthi — Iêmen",        "country": "Iêmen",   "lat": 15.35, "lon": 44.20, "severity": 4},
    {"id": "fallback-drc",     "title": "Conflito armado M23/FARDC — Leste do Congo",  "country": "Congo",   "lat": -1.67, "lon": 29.22, "severity": 4},
    {"id": "fallback-haiti",   "title": "Violência de gangues — Porto Príncipe, Haiti", "country": "Haiti",   "lat": 18.54, "lon":-72.34, "severity": 4},
    {"id": "fallback-lebanon", "title": "Tensão militar — fronteira Líbano-Israel",     "country": "Líbano",  "lat": 33.30, "lon": 35.50, "severity": 4},
    {"id": "fallback-iran",    "title": "Atividade militar e tensão regional — Irã",    "country": "Irã",     "lat": 32.00, "lon": 53.00, "severity": 3},
]

def _goldstein_to_severity(gs: float) -> int:
    """Map GoldsteinScale (-10..+10) to severity 1-5."""
    if gs <= -9:   return 5
    elif gs <= -7: return 4
    elif gs <= -5: return 3
    elif gs <= -2: return 2
    else:          return 1


def _fetch_gdelt_events(max_events: int = 200) -> list[dict]:
    """Download latest GDELT v2 Events 15-min update and extract conflict events."""
    # Get URL of latest update
    meta = requests.get(
        "http://data.gdeltproject.org/gdeltv2/lastupdate.txt", timeout=15
    )
    export_url = meta.text.strip().split("\n")[0].split(" ")[-1]

    r = requests.get(export_url, timeout=30)
    r.raise_for_status()

    # Only accept events from known active conflict country codes
    allowed_cc = set(CC_MAP.keys())

    events = []
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        fname = z.namelist()[0]
        with z.open(fname) as f:
            reader = csv.reader(
                io.TextIOWrapper(f, encoding="utf-8", errors="replace"),
                delimiter="\t"
            )
            for row in reader:
                if len(row) < 61:
                    continue
                root = row[COL_EVENT_ROOT].strip()
                if root not in CONFLICT_ROOTS:
                    continue
                cc = row[COL_ACTION_CC].strip()
                if cc not in allowed_cc:
                    continue  # skip non-conflict countries (US, UK, AU, etc.)
                try:
                    lat = float(row[COL_ACTION_LAT])
                    lon = float(row[COL_ACTION_LON])
                except (ValueError, IndexError):
                    continue
                if lat == 0.0 and lon == 0.0:
                    continue
                try:
                    gs = float(row[COL_GOLDSTEIN])
                except ValueError:
                    gs = -5.0
                try:
                    mentions = int(row[COL_MENTIONS])
                except ValueError:
                    mentions = 1
                if mentions < 2:
                    continue  # skip single-mention noise

                loc     = row[COL_ACTION_NAME].strip()
                country = CC_MAP.get(cc, loc)
                sev     = _goldstein_to_severity(gs)
                code    = row[COL_EVENT_CODE].strip()
                date    = row[COL_SQLDATE].strip()
                url     = row[COL_SOURCE_URL].strip() if len(row) > COL_SOURCE_URL else ""

                events.append({
                    "id":         f"gdelt-ev-{row[0].strip()}-{code}",
                    "title":      f"Conflito [{code}] — {loc}",
                    "country":    country,
                    "country_iso3": "UNK",
                    "lat":        lat,
                    "lon":        lon,
                    "severity":   sev,
                    "urgency":    "immediate" if sev >= 4 else "24h",
                    "crisis_type": "conflict",
                    "source":     "gdelt",
                    "people_affected": 0,
                    "mentions":   mentions,
                    "url":        url,
                    "date":       date,
                })
                if len(events) >= max_events:
                    break

    # Sort by severity desc, mentions desc
    events.sort(key=lambda e: (-e["severity"], -e.get("mentions", 0)))
    return events


@tool
def fetch_conflict_data(include_fallback: bool = True) -> list[dict]:
    """Busca dados de conflitos armados e guerras ativas via GDELT Events v2.

    Usa o banco de eventos GDELT em tempo real (atualizado a cada 15 min)
    para encontrar eventos de conflito com coordenadas geográficas precisas.
    Inclui fallback hardcoded para os maiores conflitos ativos conhecidos.

    Args:
        include_fallback: Se True, adiciona fallback para conflitos maiores
                          que podem não aparecer numa janela de 15 minutos.
    Returns:
        Lista de dicts com id, title, lat, lon, severity, crisis_type='conflict',
        source, country.
    """
    events = []
    seen_ids = set()

    # 1. GDELT Events v2 (real-time, with coordinates)
    try:
        gdelt_events = _fetch_gdelt_events(max_events=200)
        for ev in gdelt_events:
            if ev["id"] not in seen_ids:
                seen_ids.add(ev["id"])
                events.append(ev)
        print(f"GDELT Events: {len(gdelt_events)} conflitos com coordenadas")
    except Exception as e:
        print(f"GDELT Events error: {e}")

    # 2. Hardcoded fallback for major known active conflicts
    if include_fallback:
        for fb in FALLBACK_CONFLICTS:
            if fb["id"] not in seen_ids:
                seen_ids.add(fb["id"])
                events.append({
                    **fb,
                    "country_iso3": "UNK",
                    "urgency":      "immediate" if fb["severity"] >= 4 else "24h",
                    "crisis_type":  "conflict",
                    "source":       "fallback",
                    "people_affected": 0,
                })

    # Return top 50 by severity
    events.sort(key=lambda e: -e["severity"])
    return events[:50]
