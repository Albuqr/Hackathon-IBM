import requests
from ibm_watsonx_orchestrate.agent_builder.tools import tool


@tool
def fetch_usgs(min_magnitude: float = 4.5, days: int = 1) -> list[dict]:
    """Busca terremotos recentes do USGS em tempo real.

    Args:
        min_magnitude: Magnitude minima dos terremotos. Padrao: 4.5.
        days: Numero de dias para buscar. Opcoes: 1, 7, 30. Padrao: 1.
    Returns:
        Lista de dicts com id, title, lat, lon, severity, magnitude, source.
    """
    period_map = {1: "day", 7: "week", 30: "month"}
    period = period_map.get(days, "day")
    mag_map = {
        2.5: "all", 4.5: "4.5", 5.0: "significant"
    }
    mag_key = "4.5" if min_magnitude >= 4.5 else "all"
    url = f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{mag_key}_{period}.geojson"

    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        events = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            coords = feature.get("geometry", {}).get("coordinates", [0, 0, 0])
            mag = props.get("mag", 0) or 0

            if mag >= 7.5:
                severity = 5
            elif mag >= 6.5:
                severity = 4
            elif mag >= 5.5:
                severity = 3
            elif mag >= 4.5:
                severity = 2
            else:
                severity = 1

            events.append({
                "id": f"usgs-{feature.get('id', '')}",
                "title": props.get("title", ""),
                "lat": float(coords[1]),
                "lon": float(coords[0]),
                "magnitude": mag,
                "severity": severity,
                "type": "seismic",
                "source": "usgs",
                "country": "",
                "country_iso3": "UNK",
                "people_affected": 0,
                "urgency": "immediate" if severity >= 4 else "24h",
                "url": props.get("url", ""),
                "date": ""
            })
        return events
    except Exception as e:
        return [{"error": str(e), "source": "usgs"}]