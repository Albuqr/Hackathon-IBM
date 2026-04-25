import os
import sys
import json
import math
import sqlite3
import time
import asyncio
import requests
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Predictions cache ──
_predictions_cache = {"data": None, "ts": 0}

# ── Ingest tracking ──
_last_ingest = {"ts": 0, "count": 0}

load_dotenv()

app = FastAPI(title="HKTN26 Crisis API")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"])

DB = os.environ.get("DB_PATH", "data/crisis.db")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS crisis_associations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crisis_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('volunteer','org')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(crisis_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            crisis_id TEXT DEFAULT '',
            skills_needed TEXT DEFAULT '[]',
            target_volunteers INTEGER DEFAULT 10,
            start_date TEXT DEFAULT '',
            end_date TEXT DEFAULT '',
            urgency TEXT DEFAULT 'media',
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS telegram_subscribers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            username TEXT,
            country TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(telegram_id, country)
        );
        CREATE TABLE IF NOT EXISTS campaign_volunteers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER REFERENCES campaigns(id),
            volunteer_id INTEGER REFERENCES users(id),
            status TEXT DEFAULT 'selected',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(campaign_id, volunteer_id)
        );
    """)
    conn.commit()
    # Add missing columns (SQLite does not support IF NOT EXISTS for ALTER TABLE)
    for sql in [
        "ALTER TABLE users ADD COLUMN username TEXT",
        "ALTER TABLE missions ADD COLUMN crisis_id TEXT",
        "ALTER TABLE missions ADD COLUMN telegram_id INTEGER",
        "ALTER TABLE missions ADD COLUMN user_id INTEGER",
        "ALTER TABLE missions ADD COLUMN username TEXT",
    ]:
        try:
            conn.execute(sql)
            conn.commit()
        except Exception:
            pass
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

def call_orchestrate(message: str, agent_id: str = None, max_wait: int = 120) -> dict:
    base = os.environ["WO_INSTANCE"]
    token = get_wxo_token()
    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json"}
    aid = agent_id or os.environ["ORCHESTRATOR_AGENT_ID"]
    r = requests.post(
        f"{base}/v1/orchestrate/runs?stream=false",
        headers=headers,
        json={"message": {"role": "user", "content": message},
              "agent_id": aid},
        timeout=120
    )
    r.raise_for_status()
    data = r.json()
    run_id = data.get("run_id")

    interval   = 5
    iterations = max_wait // interval
    print(f"[orchestrate] run_id={run_id} | timeout={max_wait}s | polling every {interval}s (max {iterations} attempts)")

    start = time.time()
    for attempt in range(1, iterations + 1):
        time.sleep(interval)
        elapsed = time.time() - start
        r2 = requests.get(
            f"{base}/v1/orchestrate/runs/{run_id}",
            headers=headers
        )
        if r2.status_code == 200:
            run_data = r2.json()
            status   = run_data.get("status", "unknown")
            print(f"[orchestrate] attempt {attempt}/{iterations} | status={status} | elapsed={elapsed:.1f}s")
            if status == "completed":
                try:
                    content = run_data.get("result", {}).get("data", {}).get("message", {}).get("content", "")
                    if isinstance(content, list):
                        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                    print(f"[orchestrate] COMPLETED | run_id={run_id} | response: {str(content)[:500]}")
                except Exception as _le:
                    print(f"[orchestrate] COMPLETED | run_id={run_id} | (could not parse response: {_le})")
                return run_data
            elif status == "failed":
                return {"error": run_data.get("last_error")}
        else:
            print(f"[orchestrate] attempt {attempt}/{iterations} | poll HTTP {r2.status_code} | elapsed={elapsed:.1f}s")

    print(f"[orchestrate] TIMEOUT after {time.time() - start:.1f}s (limit={max_wait}s) | run_id={run_id}")
    return {"error": "timeout"}

# ── Models ──
class VolunteerCreate(BaseModel):
    name: str
    skill: str
    languages: list = ["pt-BR"]
    radius_km: float = 500
    telegram_id: int = None
    username: str = None
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

class BotMissionCreate(BaseModel):
    crisis_id: str
    telegram_id: int = None
    user_id: int = None
    username: str = None

class ChatMessage(BaseModel):
    text: str = None
    message: str = None
    user_id: int = None
    telegram_id: int = None
    username: str = None

class AssociateRequest(BaseModel):
    user_id: int
    role: str

class UserUpdate(BaseModel):
    available: bool = None
    skills: list = None

class CampaignCreate(BaseModel):
    org_id: int
    title: str
    description: str = ""
    crisis_id: str = ""
    skills_needed: list = []
    target_volunteers: int = 10
    start_date: str = ""
    end_date: str = ""
    urgency: str = "media"

class SubscribeRequest(BaseModel):
    telegram_id: int
    username: str = None
    country: str

class CampaignUpdate(BaseModel):
    title: str = None
    description: str = None
    skills_needed: list = None
    target_volunteers: int = None
    urgency: str = None
    status: str = None
    start_date: str = None
    end_date: str = None

class CampaignVolunteerAdd(BaseModel):
    volunteer_id: int
    status: str = "selected"

class CampaignVolunteerUpdate(BaseModel):
    status: str

# ── Endpoints ──
@app.get("/")
def root():
    return {"status": "ok", "service": "HKTN26 Crisis API"}

@app.get("/events")
def list_events(country: str = None, min_severity: float = 0,
                severity: int = None, crisis_type: str = None,
                limit: int = 500, order_by: str = "severity"):
    db = get_db()
    effective_min = severity if severity is not None else min_severity
    q = "SELECT * FROM crises WHERE severity >= ?"
    params = [effective_min]
    if country:
        params.extend([f"%{country}%", country])
        q += " AND (country LIKE ? OR country = ?)"
    if crisis_type:
        q += " AND crisis_type = ?"
        params.append(crisis_type)
    safe_order = "severity" if order_by not in ("severity", "created_at") else order_by
    q += f" ORDER BY {safe_order} DESC LIMIT ?"
    params.append(limit)
    rows = db.execute(q, params).fetchall()
    db.close()
    result = []
    for r in rows:
        d = dict(r)
        d["country_code"] = d.get("country_iso3", "UNK")
        result.append(d)
    return result

@app.get("/events/{crisis_id}/associations")
def get_crisis_associations(crisis_id: str, user_id: int = None):
    db = get_db()
    row = db.execute(
        """SELECT
             SUM(CASE WHEN role='volunteer' THEN 1 ELSE 0 END) as volunteers,
             SUM(CASE WHEN role='org'       THEN 1 ELSE 0 END) as orgs
           FROM crisis_associations WHERE crisis_id=?""",
        (crisis_id,)
    ).fetchone()
    user_enrolled = False
    if user_id:
        check = db.execute(
            "SELECT 1 FROM crisis_associations WHERE crisis_id=? AND user_id=?",
            (crisis_id, user_id)
        ).fetchone()
        user_enrolled = check is not None
    db.close()
    return {
        "volunteers":    row["volunteers"] or 0,
        "orgs":          row["orgs"]       or 0,
        "user_enrolled": user_enrolled,
    }

@app.post("/events/{crisis_id}/associate")
def associate_event(crisis_id: str, req: AssociateRequest):
    if req.role not in ("volunteer", "org"):
        raise HTTPException(status_code=400, detail="role must be volunteer or org")
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO crisis_associations (crisis_id, user_id, role) VALUES (?,?,?)",
        (crisis_id, req.user_id, req.role)
    )
    campaign_id = None
    if req.role == "org":
        existing = db.execute(
            "SELECT id FROM campaigns WHERE org_id=? AND crisis_id=?",
            (req.user_id, crisis_id)
        ).fetchone()
        if not existing:
            crisis_row = db.execute(
                "SELECT title FROM crises WHERE id=?", (crisis_id,)
            ).fetchone()
            draft_title = (
                f"Campanha de Apoio — {crisis_row['title']}"
                if crisis_row else f"Campanha de Apoio — {crisis_id}"
            )
            now = datetime.utcnow().isoformat()
            cur = db.execute(
                "INSERT INTO campaigns (org_id, title, description, crisis_id, "
                "skills_needed, target_volunteers, urgency, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (req.user_id, draft_title, "", crisis_id,
                 "[]", 10, "media", "pendente", now)
            )
            campaign_id = cur.lastrowid
        else:
            campaign_id = existing["id"]
    db.commit()
    db.close()
    return {"status": "ok", "campaign_id": campaign_id}

@app.delete("/events/{crisis_id}/associate/{user_id}")
def disassociate_event(crisis_id: str, user_id: int):
    db = get_db()
    db.execute(
        "DELETE FROM crisis_associations WHERE crisis_id=? AND user_id=?",
        (crisis_id, user_id)
    )
    db.commit()
    db.close()
    return {"status": "ok"}


@app.post("/volunteers")
def create_volunteer(vol: VolunteerCreate):
    db = get_db()
    cur = db.execute(
        "INSERT INTO users (name,username,skills,languages,radius_km,"
        "telegram_id,phone,lat,lon,role,available) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (vol.name, vol.username, json.dumps([vol.skill]),
         json.dumps(vol.languages), vol.radius_km,
         vol.telegram_id, vol.phone,
         vol.lat, vol.lon, "volunteer", 1)
    )
    db.commit()
    new_id = cur.lastrowid
    db.close()
    return {"id": new_id, "name": vol.name, "skill": vol.skill}

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
def create_mission(m: BotMissionCreate):
    if not m.telegram_id and not m.user_id:
        raise HTTPException(status_code=400,
                            detail="At least one of telegram_id or user_id is required")
    db = get_db()
    now = datetime.utcnow().isoformat()
    cur = db.execute(
        "INSERT INTO missions (crisis_id, telegram_id, user_id, username, status, created_at) "
        "VALUES (?, ?, ?, ?, 'active', ?)",
        (m.crisis_id, m.telegram_id, m.user_id, m.username, now)
    )
    db.commit()
    new_id = cur.lastrowid
    db.close()
    return {"id": new_id, "crisis_id": m.crisis_id, "status": "active"}

@app.get("/missions")
def list_missions(telegram_id: int = None, user_id: int = None,
                  status: str = None, org_id: int = None):
    db = get_db()
    q = """
        SELECT m.id, m.crisis_id, m.telegram_id, m.user_id, m.username,
               m.status, m.created_at,
               c.title as crisis_title, c.country, c.severity
        FROM missions m
        LEFT JOIN crises c ON m.crisis_id = c.id
        WHERE 1=1
    """
    params = []
    if telegram_id:
        q += " AND m.telegram_id = ?"
        params.append(telegram_id)
    if user_id:
        q += " AND m.user_id = ?"
        params.append(user_id)
    if status:
        q += " AND m.status = ?"
        params.append(status)
    if org_id:
        q += " AND m.org_id = ?"
        params.append(org_id)
    q += " ORDER BY m.created_at DESC"
    rows = db.execute(q, params).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.post("/subscribe")
def subscribe(req: SubscribeRequest):
    db = get_db()
    db.execute(
        "INSERT OR IGNORE INTO telegram_subscribers (telegram_id, username, country) "
        "VALUES (?, ?, ?)",
        (req.telegram_id, req.username, req.country)
    )
    db.commit()
    db.close()
    return {"ok": True, "country": req.country}

@app.get("/subscribers")
def get_subscribers(country: str):
    db = get_db()
    rows = db.execute(
        "SELECT telegram_id, username FROM telegram_subscribers WHERE country = ?",
        (country,)
    ).fetchall()
    db.close()
    return [{"telegram_id": r["telegram_id"], "username": r["username"]} for r in rows]


@app.get("/ingest/status")
def ingest_status():
    """Returns when the last ingest ran and whether data is stale (>60 min)."""
    stale_after = 60
    last_ts = _last_ingest["ts"]
    if last_ts == 0:
        last_str = None
        is_stale = True
    else:
        last_str = datetime.utcfromtimestamp(last_ts).isoformat()
        is_stale = (time.time() - last_ts) > (stale_after * 60)
    return {
        "last_ingest":         last_str,
        "events_count":        _last_ingest["count"],
        "is_stale":            is_stale,
        "stale_after_minutes": stale_after,
    }


@app.post("/save_event")
def save_event(event: dict):
    """Save a single crisis event dict to the crises table. Unauthenticated."""
    now = datetime.utcnow().isoformat()
    eid = event.get("id") or f"api-{now}"
    try:
        db = get_db()
        existing = db.execute("SELECT id FROM crises WHERE id=?", (eid,)).fetchone()
        if existing:
            db.execute(
                "UPDATE crises SET severity=?, urgency=?, crisis_type=?, updated_at=? WHERE id=?",
                (event.get("severity", 1), event.get("urgency", "monitoring"),
                 event.get("crisis_type", "humanitarian"), now, eid)
            )
        else:
            db.execute("""
                INSERT INTO crises
                (id, title, country, country_iso3, lat, lon,
                 severity, urgency, crisis_type, source,
                 people_affected, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                eid,
                event.get("title", ""),
                event.get("country", ""),
                event.get("country_iso3", "UNK"),
                float(event.get("lat", 0)),
                float(event.get("lon", 0)),
                event.get("severity", 1),
                event.get("urgency", "monitoring"),
                event.get("crisis_type", "humanitarian"),
                event.get("source", "api"),
                int(event.get("people_affected", 0)),
                now, now
            ))
        db.commit()
        db.close()
        return {"ok": True, "id": eid}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/save_events")
def save_events(events: list):
    """Save a list of crisis event dicts to the crises table. Unauthenticated."""
    now = datetime.utcnow().isoformat()
    saved = 0
    errors = []
    db = get_db()
    for event in events:
        eid = event.get("id") or f"api-{now}-{saved}"
        try:
            existing = db.execute("SELECT id FROM crises WHERE id=?", (eid,)).fetchone()
            if existing:
                db.execute(
                    "UPDATE crises SET severity=?, urgency=?, crisis_type=?, updated_at=? WHERE id=?",
                    (event.get("severity", 1), event.get("urgency", "monitoring"),
                     event.get("crisis_type", "humanitarian"), now, eid)
                )
            else:
                db.execute("""
                    INSERT INTO crises
                    (id, title, country, country_iso3, lat, lon,
                     severity, urgency, crisis_type, source,
                     people_affected, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    eid,
                    event.get("title", ""),
                    event.get("country", ""),
                    event.get("country_iso3", "UNK"),
                    float(event.get("lat", 0)),
                    float(event.get("lon", 0)),
                    event.get("severity", 1),
                    event.get("urgency", "monitoring"),
                    event.get("crisis_type", "humanitarian"),
                    event.get("source", "api"),
                    int(event.get("people_affected", 0)),
                    now, now
                ))
                saved += 1
        except Exception as e:
            errors.append({"id": eid, "error": str(e)})
    db.commit()
    db.close()
    # Update ingest tracking
    _last_ingest["ts"]    = time.time()
    _last_ingest["count"] = _last_ingest["count"] + saved
    return {"ok": True, "saved": saved, "errors": errors}


def _ingest_fallback():
    """Direct tool calls used as fallback when Orchestrate is unavailable."""
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
        _tools_dir = os.path.join(os.path.dirname(__file__), "..", "tools")
        if _tools_dir not in sys.path:
            sys.path.insert(0, _tools_dir)
        from fetch_eonet import fetch_eonet
        eonet_events = fetch_eonet(days=30, status="open")
        for ev in eonet_events:
            if ev.get("error"):
                continue
            events.append(ev)
        print(f"EONET: {len([e for e in events if e.get('source')=='eonet'])} eventos")
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
              "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
              "georss": "http://www.georss.org/georss"}
        sev_map = {"Green": 1, "Orange": 3, "Red": 5}
        type_map = {"EQ": "seismic", "TC": "meteorological",
                    "FL": "meteorological", "VO": "seismic",
                    "DR": "drought", "WF": "wildfire"}
        for item in root.findall(".//item"):
            alert = item.findtext("gdacs:alertlevel", "", ns)
            etype = item.findtext("gdacs:eventtype", "", ns)
            title = item.findtext("title", "")
            try:
                # Coordinates are nested: <geo:Point><geo:lat>...</geo:lat><geo:long>...</geo:long></geo:Point>
                lat = float(item.findtext("geo:Point/geo:lat", "0", ns))
                lon = float(item.findtext("geo:Point/geo:long", "0", ns))
                # Fallback: georss:point contains "lat lon" space-separated
                if lat == 0.0 and lon == 0.0:
                    georss_pt = item.findtext("georss:point", "", ns)
                    if georss_pt.strip():
                        parts = georss_pt.strip().split()
                        lat, lon = float(parts[0]), float(parts[1])
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

    # 4. Conflict data — GDELT Events v2 CSV (real-time, with coordinates)
    try:
        import io as _io, csv as _csv, zipfile as _zip

        # GDELT v2 column indices (confirmed from live data)
        _CONFLICT_ROOTS = {'18', '19', '20'}
        # Only FIPS country codes known to be active conflict zones
        _CC_MAP = {
            'IS':'Israel','PS':'Palestina','RS':'Rússia','UP':'Ucrânia',
            'UA':'Ucrânia','SU':'Sudão','BM':'Myanmar','YM':'Iêmen',
            'HA':'Haiti','CG':'Congo (RDC)','IR':'Irã','LE':'Líbano',
            'SY':'Síria','ET':'Etiópia','LY':'Líbia','ML':'Mali',
            'SO':'Somália','MZ':'Moçambique','AF':'Afeganistão',
            'IZ':'Iraque','PK':'Paquistão','SA':'Arábia Saudita',
        }
        # Only accept events whose ActionGeo country code is in the conflict zone list
        _ALLOWED_CC = set(_CC_MAP.keys())

        def _gs_to_sev(gs):
            if gs < -7: return 5
            elif gs < -5: return 4
            elif gs < -3: return 3
            elif gs < -1: return 2
            else: return 1

        # Get latest 15-min update URL
        meta = requests.get(
            "http://data.gdeltproject.org/gdeltv2/lastupdate.txt", timeout=15
        )
        export_url = meta.text.strip().split("\n")[0].split(" ")[-1]
        rz = requests.get(export_url, timeout=30)
        conflict_count = 0
        with _zip.ZipFile(_io.BytesIO(rz.content)) as z:
            with z.open(z.namelist()[0]) as f:
                reader = _csv.reader(
                    _io.TextIOWrapper(f, encoding="utf-8", errors="replace"),
                    delimiter="\t"
                )
                for row in reader:
                    if len(row) < 61:
                        continue
                    if row[28].strip() not in _CONFLICT_ROOTS:
                        continue
                    cc = row[53].strip()
                    if cc not in _ALLOWED_CC:
                        continue  # skip non-conflict countries
                    try:
                        lat = float(row[56]); lon = float(row[57])
                    except ValueError:
                        continue
                    if lat == 0.0 and lon == 0.0:
                        continue
                    try:
                        gs = float(row[30])
                    except ValueError:
                        gs = -5.0
                    try:
                        mentions = int(row[31])
                    except (ValueError, IndexError):
                        mentions = 1
                    if mentions < 2:
                        continue  # skip single-mention noise
                    loc     = row[52].strip()
                    country = _CC_MAP.get(cc, loc)
                    sev     = _gs_to_sev(gs)
                    code    = row[26].strip()
                    uid     = f"gdelt-ev-{row[0].strip()}-{code}"
                    events.append({
                        "id": uid, "title": f"Conflito [{code}] — {loc}",
                        "country": country, "country_iso3": "UNK",
                        "lat": lat, "lon": lon, "severity": sev,
                        "urgency": "immediate" if sev >= 4 else "24h",
                        "crisis_type": "conflict", "source": "gdelt",
                        "people_affected": 0,
                    })
                    conflict_count += 1
        print(f"GDELT Events conflict: {conflict_count} eventos com coords")
    except Exception as e:
        print(f"GDELT Events error: {e}")

    # 5. Hardcoded fallback — major known active conflicts always present
    _FALLBACK = [
        ("fallback-gaza",    "Conflito armado ativo — Gaza/Israel",          "Palestina", 31.35, 34.30, 5),
        ("fallback-ukraine", "Guerra Rússia-Ucrânia — frente leste",         "Ucrânia",   48.50, 37.50, 5),
        ("fallback-sudan",   "Guerra civil — Sudão (RSF vs Exército)",        "Sudão",     15.55, 32.53, 5),
        ("fallback-myanmar", "Conflito armado — Myanmar",                     "Myanmar",   21.00, 96.00, 4),
        ("fallback-yemen",   "Guerra civil e ataques Houthi — Iêmen",         "Iêmen",     15.35, 44.20, 4),
        ("fallback-drc",     "Conflito M23/FARDC — Leste do Congo",           "Congo",     -1.67, 29.22, 4),
        ("fallback-haiti",   "Violência de gangues — Porto Príncipe",         "Haiti",     18.54,-72.34, 4),
        ("fallback-lebanon", "Tensão militar — fronteira Líbano-Israel",      "Líbano",    33.30, 35.50, 4),
        ("fallback-iran",    "Tensão regional e atividade militar — Irã",     "Irã",       32.00, 53.00, 3),
    ]
    existing_ids = {e["id"] for e in events}
    for fid, ftitle, fcountry, flat, flon, fsev in _FALLBACK:
        if fid not in existing_ids:
            events.append({
                "id": fid, "title": ftitle, "country": fcountry,
                "country_iso3": "UNK", "lat": flat, "lon": flon,
                "severity": fsev, "urgency": "immediate" if fsev >= 4 else "24h",
                "crisis_type": "conflict", "source": "fallback",
                "people_affected": 0,
            })
    print(f"Fallback conflicts: {len(_FALLBACK)} adicionados")

    # Salvar no banco
    db = get_db()
    saved = 0
    saved_events = []
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
                saved_events.append(event)
        except Exception as e:
            print(f"DB error {event.get('id')}: {e}")
            continue

    db.commit()
    db.close()

    sources_count = {}
    for e in events:
        s = e["source"]
        sources_count[s] = sources_count.get(s, 0) + 1

    # Broadcast new crises to Telegram subscribers
    if saved_events:
        try:
            _tools_dir = os.path.join(os.path.dirname(__file__), "..", "tools")
            if _tools_dir not in sys.path:
                sys.path.insert(0, _tools_dir)
            from notify_telegram import broadcast_to_subscribers
            for ev in saved_events:
                country = ev.get("country", "")
                if country:
                    asyncio.run(broadcast_to_subscribers(
                        country=country,
                        crisis_title=ev.get("title", "Nova crise"),
                        severity=int(ev.get("severity", 1)),
                    ))
        except Exception as _be:
            print(f"[broadcast] error: {_be}")

    # Update ingest tracking
    _last_ingest["ts"]    = time.time()
    _last_ingest["count"] = saved

    return {
        "ok":              True,
        "triggered_by":    "fallback",
        "events_collected": len(events),
        "events_saved":    saved,
        "by_source":       sources_count,
    }


@app.post("/ingest")
def trigger_ingest():
    """Trigger crisis data ingestion.
    Primary path: watsonx Orchestrate monitoring_agent.
    Fallback: direct tool calls if Orchestrate fails or times out.
    """
    global _last_ingest
    vps_url    = os.environ.get("VPS_API_URL", "http://31.97.83.21:17291")
    agent_id   = os.environ.get("MONITORING_AGENT_ID",
                                os.environ.get("ORCHESTRATOR_AGENT_ID", ""))

    # ── Primary: Orchestrate ──────────────────────────────────────────
    if agent_id:
        try:
            message = (
                f"Fetch all crisis data from USGS, GDACS, EONET and conflict APIs, "
                f"classify each event, and save them to the database at {vps_url}"
            )
            print("[ingest] Trying Orchestrate monitoring_agent...")
            result = call_orchestrate(message, agent_id=agent_id, max_wait=300)
            if not result.get("error"):
                _last_ingest["ts"] = time.time()
                print("[ingest] Orchestrate path succeeded")
                return {"ok": True, "triggered_by": "orchestrate"}
            else:
                print(f"[ingest] Orchestrate returned error: {result.get('error')} — falling back")
        except Exception as e:
            print(f"[ingest] Orchestrate exception: {e} — falling back")
    else:
        print("[ingest] No agent_id configured — using fallback directly")

    # ── Fallback: direct tool calls ───────────────────────────────────
    print("[ingest] Running fallback (direct tool calls)")
    return _ingest_fallback()


@app.post("/chat")
def chat(msg: ChatMessage):
    text = msg.message or msg.text or ""
    if not text:
        return {"reply": "Mensagem vazia.", "response": "Mensagem vazia."}
    assistant_id = os.environ.get("ASSISTANT_AGENT_ID", "")
    try:
        result = call_orchestrate(text, agent_id=assistant_id or None)
        content = result["result"]["data"]["message"]["content"]
        if isinstance(content, list):
            reply = content[0].get("text", str(content))
        else:
            reply = str(content)
    except Exception:
        reply = "Agente indisponível no momento. Tente mais tarde."
    return {"reply": reply, "response": reply}

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


@app.get("/users/{user_id}")
def get_user(user_id: int):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    d = dict(row)
    d.pop("password_hash", None)
    return d

@app.put("/users/{user_id}")
def update_user(user_id: int, upd: UserUpdate):
    db = get_db()
    if upd.available is not None:
        db.execute("UPDATE users SET available=? WHERE id=?", (int(upd.available), user_id))
    if upd.skills is not None:
        db.execute("UPDATE users SET skills=? WHERE id=?", (json.dumps(upd.skills), user_id))
    db.commit()
    db.close()
    return {"status": "ok"}

@app.get("/users/{user_id}/missions")
def get_user_missions(user_id: int):
    db = get_db()
    rows = db.execute("""
        SELECT ca.crisis_id, ca.role, ca.created_at as enrolled_at,
               c.title, c.country, c.severity, c.crisis_type, c.urgency, c.lat, c.lon
        FROM crisis_associations ca
        JOIN crises c ON ca.crisis_id = c.id
        WHERE ca.user_id = ?
        ORDER BY ca.created_at DESC
    """, (user_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.post("/campaigns")
def create_campaign(c: CampaignCreate):
    db = get_db()
    now = datetime.utcnow().isoformat()
    cur = db.execute(
        "INSERT INTO campaigns (org_id, title, description, crisis_id, skills_needed, "
        "target_volunteers, start_date, end_date, urgency, status, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (c.org_id, c.title, c.description, c.crisis_id,
         json.dumps(c.skills_needed), c.target_volunteers,
         c.start_date, c.end_date, c.urgency, "active", now)
    )
    db.commit()
    campaign_id = cur.lastrowid
    db.close()
    return {"status": "created", "id": campaign_id}

@app.get("/campaigns")
def list_campaigns(org_id: int = None):
    db = get_db()
    q = """
        SELECT cam.*,
               c.title as crisis_title, c.country as crisis_country,
               c.severity as crisis_severity, c.crisis_type as crisis_type_val,
               (SELECT COUNT(*) FROM crisis_associations ca
                WHERE ca.crisis_id = cam.crisis_id AND ca.role='volunteer') as volunteer_count
        FROM campaigns cam
        LEFT JOIN crises c ON cam.crisis_id = c.id
        WHERE 1=1
    """
    params = []
    if org_id:
        q += " AND cam.org_id=?"
        params.append(org_id)
    q += " ORDER BY cam.created_at DESC"
    rows = db.execute(q, params).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int):
    db = get_db()
    row = db.execute("""
        SELECT cam.*,
               c.title as crisis_title, c.country as crisis_country,
               c.severity as crisis_severity, c.lat as crisis_lat, c.lon as crisis_lon
        FROM campaigns cam
        LEFT JOIN crises c ON cam.crisis_id = c.id
        WHERE cam.id = ?
    """, (campaign_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found")
    volunteers = db.execute("""
        SELECT u.id, u.name, u.email, u.skills, u.lat, u.lon, ca.created_at as enrolled_at
        FROM crisis_associations ca
        JOIN users u ON ca.user_id = u.id
        WHERE ca.crisis_id = ? AND ca.role = 'volunteer'
    """, (row["crisis_id"],)).fetchall()
    db.close()
    result = dict(row)
    result["volunteers"] = [dict(v) for v in volunteers]
    return result

@app.get("/campaigns/{campaign_id}/growth")
def get_campaign_growth(campaign_id: int):
    """Returns volunteer enrollment count per day for last 7 days."""
    db = get_db()
    row = db.execute("SELECT crisis_id FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found")
    rows = db.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as count
        FROM crisis_associations
        WHERE crisis_id=? AND role='volunteer'
          AND created_at >= DATE('now', '-6 days')
        GROUP BY DATE(created_at)
        ORDER BY day
    """, (row["crisis_id"],)).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.put("/campaigns/{campaign_id}")
def update_campaign(campaign_id: int, upd: CampaignUpdate):
    db = get_db()
    sets, params = [], []
    if upd.title is not None:
        sets.append("title=?"); params.append(upd.title)
    if upd.description is not None:
        sets.append("description=?"); params.append(upd.description)
    if upd.skills_needed is not None:
        sets.append("skills_needed=?"); params.append(json.dumps(upd.skills_needed))
    if upd.target_volunteers is not None:
        sets.append("target_volunteers=?"); params.append(upd.target_volunteers)
    if upd.urgency is not None:
        sets.append("urgency=?"); params.append(upd.urgency)
    if upd.status is not None:
        sets.append("status=?"); params.append(upd.status)
    if upd.start_date is not None:
        sets.append("start_date=?"); params.append(upd.start_date)
    if upd.end_date is not None:
        sets.append("end_date=?"); params.append(upd.end_date)
    if sets:
        params.append(campaign_id)
        db.execute(f"UPDATE campaigns SET {', '.join(sets)} WHERE id=?", params)
        db.commit()
    db.close()
    return {"status": "ok"}

@app.get("/campaigns/{campaign_id}/volunteers")
def list_campaign_volunteers(campaign_id: int):
    db = get_db()
    rows = db.execute("""
        SELECT cv.id, cv.volunteer_id, cv.status, cv.added_at,
               u.name, u.email, u.skills, u.lat, u.lon, u.available
        FROM campaign_volunteers cv
        JOIN users u ON cv.volunteer_id = u.id
        WHERE cv.campaign_id = ? AND cv.status != 'removed'
        ORDER BY cv.added_at DESC
    """, (campaign_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.post("/campaigns/{campaign_id}/volunteers")
def add_campaign_volunteer(campaign_id: int, req: CampaignVolunteerAdd):
    db = get_db()
    now = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO campaign_volunteers (campaign_id, volunteer_id, status, added_at) "
        "VALUES (?,?,?,?) ON CONFLICT(campaign_id, volunteer_id) DO UPDATE SET status=excluded.status",
        (campaign_id, req.volunteer_id, req.status, now)
    )
    db.commit()
    db.close()
    return {"status": "ok"}

@app.delete("/campaigns/{campaign_id}/volunteers/{volunteer_id}")
def remove_campaign_volunteer(campaign_id: int, volunteer_id: int):
    db = get_db()
    db.execute(
        "UPDATE campaign_volunteers SET status='removed' "
        "WHERE campaign_id=? AND volunteer_id=?",
        (campaign_id, volunteer_id)
    )
    db.commit()
    db.close()
    return {"status": "ok"}

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

@app.get("/volunteers/available")
def list_available_volunteers(crisis_id: str = None, radius_km: float = 1000):
    db = get_db()
    clat, clon = None, None
    if crisis_id:
        c = db.execute("SELECT lat, lon FROM crises WHERE id=?", (crisis_id,)).fetchone()
        if c:
            clat, clon = c["lat"], c["lon"]
    rows = db.execute(
        "SELECT * FROM users WHERE role='volunteer' AND lat!=0 AND lon!=0"
    ).fetchall()
    db.close()
    result = []
    for r in rows:
        d = dict(r)
        d.pop("password_hash", None)
        if clat is not None:
            dist = _haversine_km(clat, clon, d["lat"], d["lon"])
            if dist > radius_km:
                continue
            d["distance_km"] = round(dist, 1)
        else:
            d["distance_km"] = None
        result.append(d)
    if clat is not None:
        result.sort(key=lambda x: x["distance_km"] or 9999)
    return result

@app.get("/volunteer/{user_id}/campaigns")
def get_volunteer_campaigns(user_id: int):
    db = get_db()
    rows = db.execute("""
        SELECT cv.id as cv_id, cv.campaign_id, cv.status, cv.added_at,
               cam.title, cam.description, cam.urgency, cam.skills_needed,
               cam.org_id, cam.target_volunteers,
               c.title as crisis_title, c.country as crisis_country,
               c.severity as crisis_severity,
               u.name as org_name
        FROM campaign_volunteers cv
        JOIN campaigns cam ON cv.campaign_id = cam.id
        LEFT JOIN crises c ON cam.crisis_id = c.id
        LEFT JOIN users u ON cam.org_id = u.id
        WHERE cv.volunteer_id = ? AND cv.status NOT IN ('removed','declined')
        ORDER BY cv.added_at DESC
    """, (user_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

@app.get("/volunteer/{user_id}/campaigns/pending")
def get_volunteer_campaigns_pending(user_id: int):
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) as count FROM campaign_volunteers "
        "WHERE volunteer_id=? AND status='selected'",
        (user_id,)
    ).fetchone()
    db.close()
    return {"count": row["count"] if row else 0}

@app.put("/campaign_volunteers/{cv_id}")
def update_campaign_volunteer_status(cv_id: int, upd: CampaignVolunteerUpdate):
    if upd.status not in ("confirmed", "declined", "selected", "removed"):
        raise HTTPException(status_code=400, detail="invalid status")
    db = get_db()
    db.execute("UPDATE campaign_volunteers SET status=? WHERE id=?", (upd.status, cv_id))
    db.commit()
    db.close()
    return {"status": "ok"}

@app.get("/predictions")
def get_predictions():
    """Retorna previsões de risco humanitário geradas pelo Granite.
    Resultado cacheado por 1 hora para evitar chamadas excessivas ao modelo."""
    global _predictions_cache
    now = time.time()
    # Return cache if still fresh (1 hour = 3600s)
    if _predictions_cache["data"] and (now - _predictions_cache["ts"]) < 3600:
        return _predictions_cache["data"]

    # Fetch latest 50 events from DB
    db = get_db()
    rows = db.execute(
        "SELECT id, title, country, country_iso3, lat, lon, severity, "
        "urgency, crisis_type, source FROM crises "
        "ORDER BY severity DESC, created_at DESC LIMIT 50"
    ).fetchall()
    db.close()
    events = [dict(r) for r in rows]

    if not events:
        return {"predictions": [], "note": "Sem eventos no banco de dados"}

    # Call predict_humanitarian_risk via watsonx orchestrate tool directly
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    try:
        from predict_humanitarian_risk import predict_humanitarian_risk
        result_str = predict_humanitarian_risk(json.dumps(events))
        result = json.loads(result_str)
    except Exception as e:
        result = {"error": str(e), "predictions": []}

    _predictions_cache["data"] = result
    _predictions_cache["ts"]   = now
    return result