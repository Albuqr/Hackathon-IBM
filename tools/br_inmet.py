import json

import requests
from ibm_watsonx_orchestrate.agent_builder.tools import tool

URL = "https://apiprevmet3.inmet.gov.br/avisos/ativos"

SEVERIDADE = {"Perigo Potencial": 2, "Perigo": 4, "Grande Perigo": 5}

TIPO = {"seca": "drought", "baixa umidade": "drought", "incêndio": "wildfire"}


def centroide(poligono: dict) -> tuple[float, float]:
    """Centróide (lat, lon) pela fórmula de área do anel externo; média dos vértices se a área for nula."""
    anel = poligono["coordinates"][0] if poligono["type"] == "Polygon" else poligono["coordinates"][0][0]
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(anel, anel[1:] + anel[:1]):
        k = x0 * y1 - x1 * y0
        a += k
        cx += (x0 + x1) * k
        cy += (y0 + y1) * k
    if abs(a) < 1e-12:
        return sum(p[1] for p in anel) / len(anel), sum(p[0] for p in anel) / len(anel)
    a *= 0.5
    return cy / (6 * a), cx / (6 * a)


def converter_avisos(dados: dict) -> list[dict]:
    """Converte os avisos ativos do INMET (hoje e futuro) em crises, uma por aviso."""
    eventos = []
    for a in dados.get("hoje", []) + dados.get("futuro", []):
        if a.get("encerrado"):
            continue
        try:
            lat, lon = centroide(json.loads(a["poligono"]))
        except (KeyError, ValueError, TypeError, IndexError):
            continue
        sev = SEVERIDADE.get(a.get("severidade", ""), 2)
        desc = a.get("descricao", "Aviso meteorológico")
        geocodes = [int(g) for g in str(a.get("geocodes", "")).split(",") if g.strip().isdigit()]
        eventos.append({
            "id": f"inmet-{a['id_aviso']}-{a.get('id_sequencia', 1)}",
            "title": f"{desc} — {a.get('severidade', '')} (INMET)",
            "country": "Brasil",
            "country_iso3": "BRA",
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "severity": sev,
            "urgency": "immediate" if sev >= 4 else "24h",
            "crisis_type": next((t for chave, t in TIPO.items() if chave in desc.lower()), "meteorological"),
            "source": "inmet",
            "people_affected": 0,
            "municipios_afetados": geocodes,
            "link_fonte": f"https://alertas2.inmet.gov.br/{a['id_aviso']}",
            "visto_em": a.get("updated_at"),
            "expira_em": (a["fim"].replace(" ", "T") + ":00-03:00") if a.get("fim") else None,  # horário de Brasília
        })
    return eventos


@tool
def br_inmet() -> list[dict]:
    """Busca os avisos meteorológicos ativos do INMET (Alert-AS).

    Returns:
        Lista de crises, uma por aviso, com severidade (Perigo Potencial 2, Perigo 4, Grande Perigo 5),
        coordenada no centróide da área e os códigos IBGE dos municípios afetados.
    """
    try:
        r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0 (crisis-monitor-brasil)"}, timeout=30)
        r.raise_for_status()
        return converter_avisos(r.json())
    except Exception as e:
        return [{"error": str(e), "source": "inmet"}]
