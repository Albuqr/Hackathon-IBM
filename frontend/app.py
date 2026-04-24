# frontend/app.py
import os, json, hashlib, sqlite3, requests
from functools import wraps
from flask import (Flask, render_template, render_template_string,
                   request, redirect, session, jsonify)
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hktn26-dev-secret")

API = os.environ.get("API_URL", "http://localhost:8000")
DB  = os.environ.get("DB_PATH", "data/crisis.db")

# ── Helpers ───────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def api_get(path, params=None):
    try:
        r = requests.get(f"{API}{path}", params=params, timeout=10)
        return r.json()
    except:
        return []

def api_post(path, data=None):
    try:
        r = requests.post(f"{API}{path}", json=data, timeout=120)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper

# ── Auth routes ───────────────────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect("/login")
    return redirect("/map")

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        email   = request.form.get("email", "")
        pw_hash = hash_pw(request.form.get("password", ""))
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email=? AND password_hash=?",
            (email, pw_hash)
        ).fetchone()
        if user:
            session["user_id"]  = user["id"]
            session["role"]     = user["role"]
            session["name"]     = user["name"] or email
            parts = (user["name"] or email).split()
            session["initials"] = (
                parts[0][0] + (parts[-1][0] if len(parts) > 1 else parts[0][-1])
            ).upper()
            return redirect("/map")
        error = "Email ou senha incorretos"
    return render_template("login.html", error=error)

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        role     = request.form.get("role", "volunteer")
        name     = request.form.get("name", "")
        email    = request.form.get("email", "")
        password = request.form.get("password", "")
        skill    = request.form.get("skill", "")
        org_name = request.form.get("org_name", "")
        radius   = float(request.form.get("radius", 500))
        try:
            db = get_db()
            db.execute(
                "INSERT INTO users "
                "(name, email, password_hash, role, skills, languages, "
                "lat, lon, radius_km, org_name, available) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (name, email, hash_pw(password), role,
                 json.dumps([skill]), json.dumps(["pt-BR"]),
                 -23.55, -46.63, radius, org_name, 1)
            )
            db.commit()
            return redirect("/login")
        except Exception as ex:
            error = f"Erro ao cadastrar: {ex}"
    return render_template("register.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ── Main views ────────────────────────────────────────────────────────
@app.route("/map")
@require_login
def map_view():
    events = api_get("/events") or []
    stats  = api_get("/stats")  or {}
    _paises_raw = set()
    for e in events:
        for p in (e.get("country", "") or "").split(","):
            p = p.strip()
            if p:
                _paises_raw.add(p)
    paises = sorted(_paises_raw)
    return render_template("map.html",
                           events=events,
                           stats=stats,
                           paises=paises)

@app.route("/volunteer/missions")
@require_login
def vol_missions():
    if session.get("role") != "volunteer":
        return redirect("/map")
    missions = api_get("/missions") or []
    return render_template("vol_missions.html", missions=missions)

@app.route("/org/missions/new", methods=["GET", "POST"])
@require_login
def org_new_mission():
    if session.get("role") not in ("org", "admin"):
        return redirect("/map")
    if request.method == "POST":
        data = {
            "title":        request.form.get("title"),
            "description":  request.form.get("description"),
            "location":     request.form.get("location"),
            "lat":          float(request.form.get("lat", 0)),
            "lon":          float(request.form.get("lon", 0)),
            "skills_needed": request.form.get("skills_needed", ""),
            "urgency":      request.form.get("urgency", "Media"),
        }
        api_post("/missions", data)
        return redirect("/map")
    return render_template("org_mission.html")

# ── API proxy endpoints ───────────────────────────────────────────────
@app.route("/api/events")
@require_login
def api_events():
    params = dict(request.args)
    return jsonify(api_get("/events", params) or [])

@app.route("/api/stats")
@require_login
def api_stats():
    return jsonify(api_get("/stats") or {})

@app.route("/api/ingest", methods=["POST"])
@require_login
def api_ingest():
    if session.get("role") != "admin":
        return jsonify({"error": "Sem permissão"}), 403
    result = api_post("/ingest")
    return jsonify(result)

@app.route("/api/events/<crisis_id>/associations")
@require_login
def api_associations(crisis_id):
    return jsonify(api_get(f"/events/{crisis_id}/associations") or {"volunteers": 0, "orgs": 0})

@app.route("/api/chat", methods=["POST"])
@require_login
def api_chat():
    text = request.json.get("text", "")
    result = api_post("/chat", {"text": text,
                                "user_id": session.get("user_id")})
    return jsonify(result)

# ── Run ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)