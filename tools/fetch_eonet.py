import requests
from ibm_watsonx_orchestrate.agent_builder.tools import tool


CATEGORY_MAP = {
    "Wildfires":      "wildfire",
    "Severe Storms":  "meteorological",
    "Volcanoes":      "seismic",
    "Drought":        "drought",
}


@tool
def fetch_eonet(days: int = 30, status: str = "open") -> list[dict]:
    """Busca eventos de desastres naturais da NASA EONET em tempo real.

    Args:
        days: Numero de dias retroativos para buscar eventos. Padrao: 30.
        status: Status dos eventos. Opcoes: open, closed, all. Padrao: open.
    Returns:
        Lista de dicts com id, title, lat, lon, severity, crisis_type, source='eonet'.
    """
    url = "https://eonet.gsfc.nasa.gov/api/v3/events"
    params = {
        "days":   days,
        "status": status,
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        events = []
        for ev in data.get("events", []):
            # Skip events with no geometry
            geometry = ev.get("geometry", [])
            if not geometry:
                continue
            # Use the most recent geometry point
            geom = geometry[-1]
            coords = geom.get("coordinates")
            if not coords:
                continue
            # GeoJSON: [lon, lat] for Point; nested for Polygon — use first point
            if isinstance(coords[0], list):
                coords = coords[0]
            try:
                lon = float(coords[0])
                lat = float(coords[1])
            except (TypeError, ValueError, IndexError):
                continue
            if lat == 0.0 and lon == 0.0:
                continue

            ev_status = ev.get("closed") and "closed" or "open"
            severity  = 1 if ev_status == "closed" else 3

            categories = ev.get("categories", [])
            cat_title  = categories[0].get("title", "") if categories else ""
            crisis_type = CATEGORY_MAP.get(cat_title, "meteorological")

            events.append({
                "id":           f"eonet-{ev.get('id', '')}",
                "title":        ev.get("title", ""),
                "lat":          lat,
                "lon":          lon,
                "severity":     severity,
                "crisis_type":  crisis_type,
                "source":       "eonet",
                "country":      "",
                "country_iso3": "UNK",
                "people_affected": 0,
                "urgency":      "24h" if severity < 4 else "immediate",
                "url":          ev.get("sources", [{}])[0].get("url", "") if ev.get("sources") else "",
                "date":         geom.get("date", ""),
            })
        return events
    except Exception as e:
        return [{"error": str(e), "source": "eonet"}]
