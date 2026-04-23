import requests
import xml.etree.ElementTree as ET
from ibm_watsonx_orchestrate.agent_builder.tools import tool


@tool
def fetch_gdacs(alert_level: str = "orange;red") -> list[dict]:
    """Busca alertas de desastres naturais no GDACS em tempo real.

    Args:
        alert_level: Niveis de alerta separados por ponto e virgula.
                     Opcoes: green, orange, red. Padrao: orange;red.
    Returns:
        Lista de dicts com id, title, lat, lon, severity, type, source.
    """
    url = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
    params = {
        "eventlist": "EQ;TC;FL;VO;DR;WF",
        "alertlevel": alert_level
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {
            "gdacs": "http://www.gdacs.org",
            "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#"
        }
        sev_map = {"Green": 1, "Orange": 3, "Red": 5}
        type_map = {
            "EQ": "seismic", "TC": "meteorological",
            "FL": "meteorological", "VO": "seismic",
            "DR": "meteorological", "WF": "wildfire"
        }
        events = []
        for item in root.findall(".//item"):
            alert = item.findtext("gdacs:alertlevel", "", ns)
            etype = item.findtext("gdacs:eventtype", "", ns)
            try:
                lat = float(item.findtext("geo:lat", "0", ns))
                lon = float(item.findtext("geo:long", "0", ns))
            except ValueError:
                lat, lon = 0.0, 0.0
            events.append({
                "id": f"gdacs-{item.findtext('guid', '')}",
                "title": item.findtext("title", ""),
                "lat": lat,
                "lon": lon,
                "severity": sev_map.get(alert, 2),
                "type": type_map.get(etype, "unknown"),
                "source": "gdacs",
                "country": item.findtext("gdacs:country", "", ns),
                "country_iso3": item.findtext("gdacs:iso3", "", ns),
                "people_affected": 0,
                "url": item.findtext("link", "")
            })
        return events
    except Exception as e:
        return [{"error": str(e), "source": "gdacs"}]