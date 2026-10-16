import requests
from ibm_watsonx_orchestrate.agent_builder.tools import tool


@tool
def br_salvar_eventos(api_url: str, eventos: list[dict]) -> dict:
    """Salva crises brasileiras no Dash Brasil (POST {api_url}/brasil/eventos).

    Args:
        api_url: URL base da API do Crisis Monitor informada no comando.
        eventos: Crises no formato das ferramentas br_* (id, title, lat, lon, severity, crisis_type, source...).
    Returns:
        Relatório com quantas crises foram gravadas e quantas ficaram fora do Brasil.
    """
    try:
        r = requests.post(f"{api_url.rstrip('/')}/brasil/eventos", json=eventos, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}
