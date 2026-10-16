import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests
from ibm_watsonx_orchestrate.agent_builder.tools import tool

URL = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/focos_diario_br_{data}.csv"

# Cortes de severidade por nº de focos em 24h (spec FR-017; heurística a calibrar pela H2).
CORTES = [(500, 5), (200, 4), (50, 3), (10, 2), (0, 1)]
RISCO_ALTO = 0.8


def severidade(focos: int, risco_max: float) -> int:
    sev = next(s for limite, s in CORTES if focos >= limite)
    if risco_max >= RISCO_ALTO:
        sev += 1
    return min(sev, 5)


def agregar_focos(linhas, desde: datetime) -> list[dict]:
    """Agrupa focos do CSV do INPE por município (código IBGE) a partir de `desde` (UTC).

    Conta todos os focos de todos os satélites, como o INPE publica: um incêndio pode
    aparecer em mais de um satélite, por isso os cortes de severidade são uma heurística.
    """
    grupos = defaultdict(lambda: {"n": 0, "lat": 0.0, "lon": 0.0, "risco": 0.0, "ultimo": "", "nome": "", "uf": ""})
    for l in linhas:
        try:
            quando = datetime.strptime(l["data_hora_gmt"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            cod = int(l["municipio_id"])
            lat, lon = float(l["lat"]), float(l["lon"])
        except (KeyError, ValueError):
            continue
        if quando < desde:
            continue
        g = grupos[cod]
        g["n"] += 1
        g["lat"] += lat
        g["lon"] += lon
        try:
            g["risco"] = max(g["risco"], float(l.get("risco_fogo") or 0))
        except ValueError:
            pass
        g["ultimo"] = max(g["ultimo"], quando.isoformat())
        g["nome"], g["uf"] = l.get("municipio", ""), l.get("estado", "")

    eventos = []
    for cod, g in grupos.items():
        sev = severidade(g["n"], g["risco"])
        eventos.append({
            "id": f"inpe-{cod}",
            "title": f"Focos de calor — {g['nome'].title()} ({g['uf'].title()}): {g['n']} focos em 24h",
            "country": "Brasil",
            "country_iso3": "BRA",
            "lat": round(g["lat"] / g["n"], 5),
            "lon": round(g["lon"] / g["n"], 5),
            "severity": sev,
            "urgency": "immediate" if sev >= 4 else "24h" if sev == 3 else "48h",
            "crisis_type": "wildfire",
            "source": "inpe",
            "people_affected": 0,
            "municipio_ibge": cod,
            "link_fonte": "https://terrabrasilis.dpi.inpe.br/queimadas/portal/",
            "visto_em": g["ultimo"],
            "focos": g["n"],
        })
    return eventos


@tool
def br_inpe_queimadas(horas: int = 24) -> list[dict]:
    """Busca focos de calor do INPE (Programa Queimadas) e agrega por município brasileiro.

    Args:
        horas: Janela em horas a partir de agora. Padrão: 24.
    Returns:
        Lista de crises do tipo wildfire, uma por município, com severidade 1–5 e código IBGE.
    """
    agora = datetime.now(timezone.utc)
    linhas, erros = [], []
    for dia in (agora - timedelta(days=1), agora):
        try:
            r = requests.get(URL.format(data=dia.strftime("%Y%m%d")), timeout=60)
            r.raise_for_status()
            linhas.extend(csv.DictReader(io.StringIO(r.content.decode("utf-8", errors="ignore"))))
        except Exception as e:
            erros.append(str(e))
    if not linhas:
        return [{"error": "; ".join(erros) or "sem dados", "source": "inpe"}]
    return agregar_focos(linhas, agora - timedelta(hours=horas))
