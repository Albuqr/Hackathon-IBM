import requests
from datetime import datetime, timedelta
from ibm_watsonx_orchestrate.agent_builder.tools import tool


@tool
def fetch_conflict_data(days_back: int = 3) -> list[dict]:
    """Busca dados de conflitos armados e instabilidade política em tempo real via GDELT Project.

    Args:
        days_back: Quantos dias atrás buscar eventos. Padrão: 3.
    Returns:
        Lista de dicts com id, title, lat, lon, severity, crisis_type='conflict', source.
    """
    events = []

    # ── GDELT GKG / Event API (sem autenticação, completamente gratuito) ──
    try:
        # GDELT Events API v2 — filtra por categoria de conflito/violência
        # Códigos de evento CAMEO relacionados a conflito:
        # 14=Protest, 17=Coerce, 18=Assault, 19=Fight, 20=Use conventional force
        since = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y%m%d%H%M%S")
        url = "https://api.gdeltproject.org/api/v2/events/query"
        params = {
            "query": "eventcode:14 OR eventcode:17 OR eventcode:18 OR eventcode:19 OR eventcode:20",
            "mode": "artlist",
            "maxrecords": 75,
            "startdatetime": since,
            "format": "json",
            "sourcelang": "eng",
        }
        r = requests.get(url, params=params, timeout=20)
        if r.status_code == 200:
            data = r.json()
            for art in data.get("articles", []):
                # GDELT GKG article — extract what we can
                title = art.get("title", "")
                url_src = art.get("url", "")
                # No direct lat/lon in artlist mode — skip entries without geo
                # Use a simpler GDELT endpoint instead (see below)
            print(f"GDELT artlist: tentativa (sem coords diretas)")
    except Exception as e:
        print(f"GDELT artlist error: {e}")

    # ── GDELT Events API — tabular mode with coordinates ──
    try:
        # GDELT 2.0 Event Database — last 15 minutes update files are free
        # Use the geo-coded event search
        url2 = "https://api.gdeltproject.org/api/v2/events/query"
        params2 = {
            "query": "eventcode:180 OR eventcode:190 OR eventcode:200 OR eventcode:1821 OR eventcode:1831",
            "mode": "timelinecountry",
            "format": "json",
        }
        # Fallback: use GDELT DOC 2.0 fulltext search for conflict news
        doc_url = "https://api.gdeltproject.org/api/v2/doc/doc"
        doc_params = {
            "query": "conflict war attack battle casualties",
            "mode": "artlist",
            "maxrecords": 50,
            "format": "json",
            "sort": "DateDesc",
        }
        r2 = requests.get(doc_url, params=doc_params, timeout=20)
        if r2.status_code == 200:
            data2 = r2.json()
            seen = set()
            for art in data2.get("articles", []):
                title = art.get("title", "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                # GDELT doc API does not always include lat/lon
                # Extract country from socialimage or domain heuristics
                domain = art.get("domain", "")
                lang   = art.get("language", "")
                # Assign a rough severity based on keywords in title
                tl = title.lower()
                if any(k in tl for k in ["massacre", "genocide", "mass casualty", "siege", "major offensive"]):
                    sev = 5
                elif any(k in tl for k in ["war", "battle", "offensive", "airstrike", "bombing"]):
                    sev = 4
                elif any(k in tl for k in ["conflict", "fighting", "clashes", "attack", "gunfire"]):
                    sev = 3
                elif any(k in tl for k in ["protest", "demonstration", "unrest", "tension"]):
                    sev = 2
                else:
                    sev = 2

                events.append({
                    "id": f"gdelt-{abs(hash(title)) % 10**9}",
                    "title": title,
                    "country": "",
                    "country_iso3": "UNK",
                    "lat": 0.0,
                    "lon": 0.0,
                    "severity": sev,
                    "urgency": "immediate" if sev >= 4 else "24h",
                    "crisis_type": "conflict",
                    "source": "gdelt",
                    "people_affected": 0,
                    "url": art.get("url", ""),
                })
        print(f"GDELT doc: {len([e for e in events if e['source']=='gdelt'])} eventos")
    except Exception as e:
        print(f"GDELT doc error: {e}")

    # ── ACLED (Armed Conflict Location & Event Data) — public data endpoint ──
    # ACLED requires registration but offers a free public data API
    # We use ReliefWeb as a reliable free alternative for conflict events
    try:
        rw_url = "https://api.reliefweb.int/v1/reports"
        rw_params = {
            "appname": "hktn26-crisis-monitor",
            "filter[field]": "theme.name",
            "filter[value][]": ["Conflict and Violence", "Safety and Security"],
            "fields[include][]": ["title", "country", "date", "body"],
            "limit": 30,
            "sort[]": "date:desc",
        }
        r3 = requests.get(rw_url, params=rw_params, timeout=15)
        if r3.status_code == 200:
            for item in r3.json().get("data", []):
                fields = item.get("fields", {})
                title  = fields.get("title", "")
                countries = fields.get("country", [{}])
                country_name = countries[0].get("name", "") if countries else ""

                tl = title.lower()
                if any(k in tl for k in ["massacre", "mass casualty", "siege", "major offensive"]):
                    sev = 5
                elif any(k in tl for k in ["war", "battle", "offensive", "airstrike"]):
                    sev = 4
                elif any(k in tl for k in ["conflict", "clashes", "attack", "armed"]):
                    sev = 3
                else:
                    sev = 2

                events.append({
                    "id": f"reliefweb-conflict-{item.get('id', abs(hash(title)) % 10**9)}",
                    "title": title,
                    "country": country_name,
                    "country_iso3": "UNK",
                    "lat": 0.0,
                    "lon": 0.0,
                    "severity": sev,
                    "urgency": "immediate" if sev >= 4 else "24h",
                    "crisis_type": "conflict",
                    "source": "reliefweb-conflict",
                    "people_affected": 0,
                })
        print(f"ReliefWeb conflict: {len([e for e in events if e['source']=='reliefweb-conflict'])} eventos")
    except Exception as e:
        print(f"ReliefWeb conflict error: {e}")

    return events
