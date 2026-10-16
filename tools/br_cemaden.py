import requests
from ibm_watsonx_orchestrate.agent_builder.tools import tool

URL = "https://painelalertas.cemaden.gov.br/wsAlertas2"

NIVEL = {"Moderado": 3, "Alto": 4, "Muito Alto": 5}


def tipo_do_evento(evento: str) -> str:
    e = evento.lower()
    if "hidrol" in e:
        return "meteorological"
    if "geol" in e or "massa" in e:
        return "geological"
    return "meteorological"


def converter_alertas(dados: dict) -> list[dict]:
    """Converte a resposta do CEMADEN em crises (só alertas ativos, status 1)."""
    eventos = []
    for a in dados.get("alertas", []):
        if a.get("status") != 1:
            continue
        sev = NIVEL.get(a.get("nivel", ""), 3)
        eventos.append({
            "id": f"cemaden-{a['cod_alerta']}",
            "title": f"{a.get('evento', 'Alerta')} — {str(a.get('municipio', '')).title()} ({a.get('uf', '')})",
            "country": "Brasil",
            "country_iso3": "BRA",
            "lat": float(a["latitude"]),
            "lon": float(a["longitude"]),
            "severity": sev,
            "urgency": "immediate" if sev >= 4 else "24h",
            "crisis_type": tipo_do_evento(a.get("evento", "")),
            "source": "cemaden",
            "people_affected": 0,
            "municipio_ibge": int(a["codibge"]) if a.get("codibge") else None,
            "link_fonte": "https://painelalertas.cemaden.gov.br/",
            "visto_em": a.get("ult_atualizacao") or a.get("datahoracriacao"),
        })
    return eventos


@tool
def br_cemaden() -> list[dict]:
    """Busca os alertas ativos de risco hidrológico e geológico do CEMADEN.

    Returns:
        Lista de crises, uma por alerta, com severidade (Moderado 3, Alto 4, Muito Alto 5) e código IBGE.
    """
    try:
        r = requests.get(URL, timeout=30)
        r.raise_for_status()
        return converter_alertas(r.json())
    except Exception as e:
        return [{"error": str(e), "source": "cemaden"}]
