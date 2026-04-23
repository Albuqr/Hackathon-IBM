import requests
from ibm_watsonx_orchestrate.agent_builder.tools import tool


@tool
def fetch_reliefweb(limit: int = 50) -> list[dict]:
    """Busca desastres humanitarios ativos no ReliefWeb da ONU.

    Args:
        limit: Numero maximo de desastres a retornar. Padrao: 50.
    Returns:
        Lista de dicts com id, title, country, country_iso3, type, date, source.
    """
    url = "https://api.reliefweb.int/v2/disasters"
    params = {
        "appname": "hktn26-crisis",
        "filter[field]": "status",
        "filter[value]": "current",
        "limit": limit,
        "sort[]": "date:desc",
        "fields[include][]": ["name", "country", "type", "date", "url"]
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        events = []
        for d in data.get("data", []):
            f = d.get("fields", {})
            country = f.get("country", [{}])[0]
            dtype = f.get("type", [{}])[0]
            type_map = {
                "Flood": "meteorological",
                "Earthquake": "seismic",
                "Epidemic": "sanitary",
                "Drought": "meteorological",
                "Cyclone": "meteorological",
                "Volcano": "seismic",
                "Fire": "wildfire",
                "Conflict": "humanitarian",
                "Tsunami": "seismic",
                "Landslide": "meteorological"
            }
            raw_type = dtype.get("name", "unknown")
            events.append({
                "id": f"reliefweb-{d['id']}",
                "title": f.get("name", ""),
                "country": country.get("name", ""),
                "country_iso3": country.get("iso3", "UNK"),
                "lat": float(country.get("location", {}).get("lat", 0)),
                "lon": float(country.get("location", {}).get("lon", 0)),
                "type": type_map.get(raw_type, "humanitarian"),
                "date": f.get("date", {}).get("created", ""),
                "source": "reliefweb",
                "raw_description": raw_type,
                "people_affected": 0,
                "url": f.get("url", "")
            })
        return events
    except Exception as e:
        return [{"error": str(e), "source": "reliefweb"}]