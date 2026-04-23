import os
import json
import sqlite3
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="HKTN26 Crisis API")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"])

DB = os.environ.get("DB_PATH", "data/crisis.db")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# ── Token cache ──
_token_cache = {"token": None, "exp": 0}

def get_wxo_token():
    if _token_cache["token"] and time.time() < _token_cache["exp"] - 60:
        return _token_cache["token"]
    r = requests.post(
        "https://iam.cloud.ibm.com/identity/token",
        data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey",
              "apikey": os.environ["WO_API_KEY"]}
    )
    r.raise_for_status()
    d = r.json()
    _token_cache["token"] = d["access_token"]
    _token_cache["exp"] = time.time() + d["expires_in"]
    return _token_cache["token"]

def call_orchestrate(message: str) -> dict:
    base = os.environ["WO_INSTANCE"]
    token = get_wxo_token()
    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json"}
    r = requests.post(
        f"{base}/v1/orchestrate/runs?stream=false",
        headers=headers,
        json={"message": {"role": "user", "content": message},
              "agent_id": os.environ["ORCHESTRATOR_AGENT_ID"]},
        timeout=120
    )
    r.raise_for_status()
    data = r.json()
    run_id = data.get("run_id")

    # Aguardar conclusão
    for _ in range(24):
        time.sleep(5)
        r2 = requests.get(
            f"{base}/v1/orchestrate/runs/{run_id}",
            headers=headers
        )
        if r2.status_code == 200:
            run_data = r2.json()
            if run_data.get("status") == "completed":
                return run_data
            elif run_data.get("status") == "failed":
                return {"error": run_data.get("last_error")}
    return {"error": "timeout"}

# ── Models ──
class VolunteerCreate(BaseModel):
    name: str
    skill: str
    languages: list = ["pt-BR"]
    radius_km: float = 500
    telegram_id: int = None
    phone: str = None
    lat: float = 0
    lon: float = 0

class MissionCreate(BaseModel):
    title: str
    description: str
    location: str
    lat: float = 0
    lon: float = 0
    skills: list = []
    urgency: str = "Media"
    org_id: int = None

class ChatMessage(BaseModel):
    text: str
    user_id: int = None

# ── Endpoints ──
@app.get("/")
def root():
    return {"status": "ok", "service": "HKTN26 Crisis API"}

@app.get("/events")
def list_events(country: str = None, min_severity: float = 0,
                crisis_type: str = None, limit: int = 200):
    db = get_db()
    q = "SELECT * FROM crises WHERE severity >= ?"
    params = [min_severity]
    if country:
        q += " AND country_iso3 = ?"
        params.append(country)
    if crisis_type:
        q += " AND crisis_type = ?"
        params.append(crisis_type)
    q += " ORDER BY severity DESC LIMIT ?"
    params.append(limit)
    rows = db.execute(q, params).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.post("/volunteers")
def create_volunteer(vol: VolunteerCreate):
    db = get_db()
    db.execute(
        "INSERT INTO users (name,skills,languages,radius_km,"
        "telegram_id,phone,lat,lon,role,available) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (vol.name, json.dumps([vol.skill]),
         json.dumps(vol.languages), vol.radius_km,
         vol.telegram_id, vol.phone,
         vol.lat, vol.lon, "volunteer", 1)
    )
    db.commit()
    db.close()
    return {"status": "ok", "name": vol.name}

@app.get("/volunteers")
def list_volunteers(skill: str = None, available: bool = True):
    db = get_db()
    q = "SELECT * FROM users WHERE role='volunteer' AND available=?"
    params = [available]
    if skill:
        q += " AND skills LIKE ?"
        params.append(f"%{skill}%")
    rows = db.execute(q, params).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.post("/missions")
def create_mission(m: MissionCreate):
    db = get_db()
    db.execute(
        "INSERT INTO missions (title,description,location,"
        "lat,lon,skills_needed,urgency,org_id) VALUES (?,?,?,?,?,?,?,?)",
        (m.title, m.description, m.location,
         m.lat, m.lon, json.dumps(m.skills),
         m.urgency, m.org_id)
    )
    db.commit()
    db.close()
    # Disparar ingestão
    return {"status": "created"}

@app.get("/missions")
def list_missions(status: str = None, org_id: int = None):
    db = get_db()
    q = "SELECT * FROM missions WHERE 1=1"
    params = []
    if status:
        q += " AND status=?"
        params.append(status)
    if org_id:
        q += " AND org_id=?"
        params.append(org_id)
    q += " ORDER BY created_at DESC"
    rows = db.execute(q, params).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.post("/subscribe")
def subscribe(user_id: int, country: str):
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO subscriptions VALUES (?,?)",
        (user_id, country)
    )
    db.commit()
    db.close()
    return {"status": "subscribed"}

@app.get("/subscribers")
def get_subscribers(country: str):
    db = get_db()
    rows = db.execute(
        "SELECT user_id FROM subscriptions WHERE country_iso3=?",
        (country,)
    ).fetchall()
    db.close()
    return [r["user_id"] for r in rows]


@app.post("/ingest")
def trigger_ingest():
    import xml.etree.ElementTree as ET
    import re as _re
    events = []
    now = datetime.utcnow().isoformat()

    # 1. USGS Earthquakes
    try:
        r = requests.get(
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson",
            timeout=15
        )
        for f in r.json().get("features", []):
            p = f.get("properties", {})
            c = f.get("geometry", {}).get("coordinates", [0, 0])
            mag = p.get("mag", 0) or 0
            if mag >= 7.5: sev = 5
            elif mag >= 6.5: sev = 4
            elif mag >= 5.5: sev = 3
            elif mag >= 4.5: sev = 2
            else: sev = 1
            place = p.get("place", "")
            country = place.split(", ")[-1] if ", " in place else ""
            events.append({
                "id": f"usgs-{f.get('id','')}",
                "title": p.get("title", ""),
                "country": country,
                "country_iso3": "UNK",
                "lat": float(c[1]),
                "lon": float(c[0]),
                "severity": sev,
                "urgency": "immediate" if sev >= 4 else "24h",
                "crisis_type": "seismic",
                "source": "usgs",
                "people_affected": 0
            })
        print(f"USGS: {len([e for e in events if e['source']=='usgs'])} eventos")
    except Exception as e:
        print(f"USGS error: {e}")

    # 2. NASA EONET
    try:
        r = requests.get(
            "https://eonet.gsfc.nasa.gov/api/v3/events",
            params={"status": "open", "limit": 50},
            timeout=15
        )
        cat_map = {
            "Wildfires": "wildfire",
            "Severe Storms": "meteorological",
            "Volcanoes": "seismic",
            "Floods": "meteorological",
            "Earthquakes": "seismic",
            "Drought": "drought",
            "Sea and Lake Ice": "meteorological",
            "Landslides": "meteorological"
        }
        cat_sev = {
            "Wildfires": 3, "Severe Storms": 4,
            "Volcanoes": 4, "Floods": 3,
            "Earthquakes": 3, "Drought": 2,
            "Landslides": 3
        }
        for ev in r.json().get("events", []):
            cat = ev.get("categories", [{}])[0].get("title", "")
            geo = ev.get("geometry", [{}])
            coords = geo[-1].get("coordinates", [0, 0]) if geo else [0, 0]
            try:
                lon = float(coords[0])
                lat = float(coords[1])
            except:
                lat, lon = 0.0, 0.0

            # Fix: queimas controladas = severidade 1
            title_lower = ev.get("title", "").lower()
            is_prescribed = any(x in title_lower for x in
                ["prescribed", " rx ", "rx-", "burn unit", "rxfire"])
            sev = 1 if is_prescribed else cat_sev.get(cat, 2)

            events.append({
                "id": f"eonet-{ev.get('id','')}",
                "title": ev.get("title", ""),
                "country": "",
                "country_iso3": "UNK",
                "lat": lat,
                "lon": lon,
                "severity": sev,
                "urgency": "24h" if sev >= 3 else "monitoring",
                "crisis_type": cat_map.get(cat, "humanitarian"),
                "source": "eonet",
                "people_affected": 0
            })
        print(f"EONET: {len([e for e in events if e['source']=='eonet'])} eventos")
    except Exception as e:
        print(f"EONET error: {e}")

    # 3. GDACS via RSS
    try:
        r = requests.get(
            "https://www.gdacs.org/xml/rss.xml",
            headers={"User-Agent": "hktn26/1.0"},
            timeout=15
        )
        content = r.content
        if content.startswith(b'\xef\xbb\xbf'):
            content = content[3:]
        content = content.decode('utf-8', errors='ignore').encode('utf-8')
        root = ET.fromstring(content)
        ns = {"gdacs": "http://www.gdacs.org",
              "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#"}
        sev_map = {"Green": 1, "Orange": 3, "Red": 5}
        type_map = {"EQ": "seismic", "TC": "meteorological",
                    "FL": "meteorological", "VO": "seismic",
                    "DR": "drought", "WF": "wildfire"}
        for item in root.findall(".//item"):
            alert = item.findtext("gdacs:alertlevel", "", ns)
            etype = item.findtext("gdacs:eventtype", "", ns)
            title = item.findtext("title", "")
            try:
                lat = float(item.findtext("geo:lat", "0", ns))
                lon = float(item.findtext("geo:long", "0", ns))
            except:
                lat, lon = 0.0, 0.0

            # Fix: calcular severidade real pelo magnitude
            sev = sev_map.get(alert, 2)
            if etype == "EQ":
                mag_match = _re.search(r'Magnitude\s+([\d.]+)', title)
                if mag_match:
                    mag = float(mag_match.group(1))
                    if mag >= 7.5: sev = 5
                    elif mag >= 6.5: sev = 4
                    elif mag >= 5.5: sev = 3
                    elif mag >= 4.5: sev = 2
                    else: sev = 1

            events.append({
                "id": f"gdacs-{item.findtext('guid', title)}",
                "title": title,
                "country": item.findtext("gdacs:country", "", ns),
                "country_iso3": item.findtext("gdacs:iso3", "UNK", ns),
                "lat": lat, "lon": lon,
                "severity": sev,
                "urgency": "immediate" if sev >= 4 else "24h",
                "crisis_type": type_map.get(etype, "humanitarian"),
                "source": "gdacs",
                "people_affected": 0
            })
        print(f"GDACS: {len([e for e in events if e['source']=='gdacs'])} eventos")
    except Exception as e:
        print(f"GDACS error: {e}")

    # Salvar no banco
    db = get_db()
    saved = 0
    for event in events:
        if not event.get("id"):
            continue
        try:
            existing = db.execute(
                "SELECT id FROM crises WHERE id=?", (event["id"],)
            ).fetchone()
            if not existing:
                db.execute("""
                    INSERT INTO crises
                    (id, title, country, country_iso3, lat, lon,
                     severity, urgency, crisis_type, source,
                     people_affected, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    event["id"], event["title"],
                    event["country"], event["country_iso3"],
                    event["lat"], event["lon"],
                    event["severity"], event["urgency"],
                    event["crisis_type"], event["source"],
                    event["people_affected"], now, now
                ))
                saved += 1
        except Exception as e:
            print(f"DB error {event.get('id')}: {e}")
            continue

    db.commit()
    db.close()

    sources_count = {}
    for e in events:
        s = e["source"]
        sources_count[s] = sources_count.get(s, 0) + 1

    return {
        "status": "ok",
        "events_collected": len(events),
        "events_saved": saved,
        "by_source": sources_count
    }

@app.post("/chat")
def chat(msg: ChatMessage):
    result = call_orchestrate(msg.text)
    try:
        content = result["result"]["data"]["message"]["content"]
        if isinstance(content, list):
            reply = content[0].get("text", str(content))
        else:
            reply = str(content)
    except Exception:
        reply = "Sem resposta disponivel."
    return {"reply": reply}

@app.get("/stats")
def get_stats():
    db = get_db()
    stats = {
        "crises": db.execute("SELECT COUNT(*) FROM crises").fetchone()[0],
        "volunteers": db.execute(
            "SELECT COUNT(*) FROM users WHERE role='volunteer'"
        ).fetchone()[0],
        "missions": db.execute("SELECT COUNT(*) FROM missions").fetchone()[0],
        "matches": db.execute("SELECT COUNT(*) FROM matches").fetchone()[0],
        "high_severity": db.execute(
            "SELECT COUNT(*) FROM crises WHERE severity >= 4"
        ).fetchone()[0],
    }
    db.close()
    return stats