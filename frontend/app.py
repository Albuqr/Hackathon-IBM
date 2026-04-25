# frontend/app.py
import os, json, hashlib, sqlite3, requests, threading
from functools import wraps
from flask import (Flask, render_template, request,
                   redirect, session, jsonify)
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "hktn26-dev-secret")

API        = os.environ.get("API_URL", "http://localhost:8000")
DB         = os.environ.get("DB_PATH", "data/crisis.db")
STADIA_KEY = os.environ.get("STADIA_API_KEY", "")

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

def api_put(path, data=None):
    try:
        r = requests.put(f"{API}{path}", json=data, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def api_delete(path):
    try:
        r = requests.delete(f"{API}{path}", timeout=10)
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

def _maybe_trigger_ingest():
    """Fire a background ingest if data is stale. Non-blocking."""
    try:
        status = api_get("/ingest/status") or {}
        if status.get("is_stale", True):
            threading.Thread(
                target=api_post, args=("/ingest",), daemon=True
            ).start()
            return True   # refreshing
    except Exception:
        pass
    return False  # fresh


def _build_map_context():
    """Shared context builder for all map views."""
    refreshing = _maybe_trigger_ingest()
    events = api_get("/events", {"limit": 500}) or []
    stats  = api_get("/stats")  or {}
    paises = sorted(set(
        p.strip()
        for e in events
        for p in (e.get("country", "") or "").split(",")
        if p.strip()
    ))
    return events, stats, paises, refreshing

def _get_enrolled_ids(user_id):
    """Return set of crisis_ids this user is enrolled in."""
    db = get_db()
    rows = db.execute(
        "SELECT crisis_id FROM crisis_associations WHERE user_id=?", (user_id,)
    ).fetchall()
    db.close()
    return [r["crisis_id"] for r in rows]

# ── Auth routes ───────────────────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect("/login")
    role = session.get("role")
    if role == "volunteer":
        return redirect("/volunteer/map")
    elif role == "org":
        return redirect("/org/map")
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
            role = user["role"]
            if role == "volunteer":
                return redirect("/volunteer/map")
            elif role == "org":
                return redirect("/org/map")
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
                 json.dumps([skill] if skill else []), json.dumps(["pt-BR"]),
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

# ── Admin map ─────────────────────────────────────────────────────────
@app.route("/map")
@require_login
def map_view():
    role = session.get("role")
    if role == "volunteer":
        return redirect("/volunteer/map")
    if role == "org":
        return redirect("/org/map")
    events, stats, paises, refreshing = _build_map_context()
    return render_template("map.html", events=events, stats=stats,
                           paises=paises, map_mode="admin", enrolled_ids=[],
                           stadia_key=STADIA_KEY, refreshing=refreshing)

# ── Volunteer routes ──────────────────────────────────────────────────
@app.route("/volunteer/map")
@require_login
def volunteer_map():
    if session.get("role") == "admin":
        return redirect("/map")
    if session.get("role") == "org":
        return redirect("/org/map")
    events, stats, paises, refreshing = _build_map_context()
    enrolled = _get_enrolled_ids(session["user_id"])
    return render_template("map.html", events=events, stats=stats,
                           paises=paises, map_mode="volunteer",
                           enrolled_ids=enrolled, stadia_key=STADIA_KEY,
                           refreshing=refreshing)

@app.route("/volunteer/profile")
@require_login
def volunteer_profile():
    if session.get("role") not in ("volunteer", "admin"):
        return redirect("/org/dashboard")
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?",
                      (session["user_id"],)).fetchone()
    db.close()
    if not user:
        return redirect("/logout")
    user = dict(user)
    user["skills_list"] = json.loads(user.get("skills") or "[]")
    missions = api_get(f"/users/{session['user_id']}/missions") or []
    return render_template("volunteer_profile.html", user=user, missions=missions)

@app.route("/volunteer/missions")
@require_login
def vol_missions():
    return redirect("/volunteer/profile")

@app.route("/volunteer/campaigns")
@require_login
def volunteer_campaigns():
    if session.get("role") not in ("volunteer", "admin"):
        return redirect("/org/dashboard")
    campaigns = api_get(f"/volunteer/{session['user_id']}/campaigns") or []
    pending = api_get(f"/volunteer/{session['user_id']}/campaigns/pending") or {"count": 0}
    return render_template("volunteer_campaigns.html",
                           campaigns=campaigns,
                           pending_count=pending.get("count", 0))

# ── ONG routes ────────────────────────────────────────────────────────
@app.route("/org/map")
@require_login
def org_map():
    if session.get("role") == "admin":
        return redirect("/map")
    if session.get("role") == "volunteer":
        return redirect("/volunteer/map")
    events, stats, paises, refreshing = _build_map_context()
    enrolled = _get_enrolled_ids(session["user_id"])
    return render_template("map.html", events=events, stats=stats,
                           paises=paises, map_mode="org",
                           enrolled_ids=enrolled, stadia_key=STADIA_KEY,
                           refreshing=refreshing)

@app.route("/org/dashboard")
@require_login
def org_dashboard():
    if session.get("role") not in ("org", "admin"):
        return redirect("/volunteer/map")
    campaigns = api_get(f"/campaigns?org_id={session['user_id']}") or []
    stats = api_get("/stats") or {}

    # Per-campaign bar chart: volunteer count per campaign
    chart_labels = json.dumps([c.get("title", "")[:20] for c in campaigns])
    chart_data   = json.dumps([c.get("volunteer_count", 0) or 0 for c in campaigns])

    # Metrics
    total_volunteers = sum(c.get("volunteer_count", 0) or 0 for c in campaigns)
    active_campaigns = sum(1 for c in campaigns if c.get("status") == "active")
    crises_supported = len(set(c.get("crisis_id") for c in campaigns if c.get("crisis_id")))

    return render_template("org_dashboard.html",
                           campaigns=campaigns,
                           chart_labels=chart_labels,
                           chart_data=chart_data,
                           total_volunteers=total_volunteers,
                           active_campaigns=active_campaigns,
                           crises_supported=crises_supported,
                           stats=stats)

@app.route("/org/campaigns/new", methods=["GET", "POST"])
@require_login
def org_campaign_new():
    if session.get("role") not in ("org", "admin"):
        return redirect("/volunteer/map")
    if request.method == "POST":
        skills_raw = request.form.getlist("skills_needed")
        data = {
            "org_id":           session["user_id"],
            "title":            request.form.get("title", ""),
            "description":      request.form.get("description", ""),
            "crisis_id":        request.form.get("crisis_id", ""),
            "skills_needed":    skills_raw,
            "target_volunteers": int(request.form.get("target_volunteers", 10)),
            "start_date":       request.form.get("start_date", ""),
            "end_date":         request.form.get("end_date", ""),
            "urgency":          request.form.get("urgency", "media"),
        }
        result = api_post("/campaigns", data)
        if result.get("status") == "created":
            return redirect("/org/dashboard")
    events = api_get("/events") or []
    return render_template("org_campaign_new.html", events=events)

@app.route("/org/campaigns/<int:campaign_id>")
@require_login
def org_campaign_detail(campaign_id):
    if session.get("role") not in ("org", "admin"):
        return redirect("/volunteer/map")
    campaign = api_get(f"/campaigns/{campaign_id}")
    if not campaign or isinstance(campaign, list):
        return redirect("/org/dashboard")
    return render_template("org_campaign_detail.html", campaign=campaign)

@app.route("/org/missions/new", methods=["GET", "POST"])
@require_login
def org_new_mission():
    return redirect("/org/campaigns/new")

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
    return jsonify(api_post("/ingest"))

@app.route("/api/events/<crisis_id>/associations")
@require_login
def api_associations(crisis_id):
    params = {"user_id": session.get("user_id")}
    return jsonify(api_get(f"/events/{crisis_id}/associations", params)
                   or {"volunteers": 0, "orgs": 0, "user_enrolled": False})

@app.route("/api/events/<crisis_id>/associate", methods=["POST"])
@require_login
def api_associate(crisis_id):
    role = session.get("role")
    if role not in ("volunteer", "org"):
        return jsonify({"error": "invalid role"}), 400
    return jsonify(api_post(f"/events/{crisis_id}/associate",
                            {"user_id": session["user_id"], "role": role}))

@app.route("/api/events/<crisis_id>/disassociate", methods=["POST"])
@require_login
def api_disassociate(crisis_id):
    return jsonify(api_delete(f"/events/{crisis_id}/associate/{session['user_id']}"))

@app.route("/api/users/<int:user_id>", methods=["PUT"])
@require_login
def api_update_user(user_id):
    if session.get("user_id") != user_id:
        return jsonify({"error": "forbidden"}), 403
    return jsonify(api_put(f"/users/{user_id}", request.json))

@app.route("/api/users/<int:user_id>/missions")
@require_login
def api_user_missions(user_id):
    return jsonify(api_get(f"/users/{user_id}/missions") or [])

@app.route("/api/campaigns", methods=["GET"])
@require_login
def api_campaigns_list():
    params = dict(request.args)
    return jsonify(api_get("/campaigns", params) or [])

@app.route("/api/campaigns", methods=["POST"])
@require_login
def api_campaigns_create():
    data = request.json or {}
    data["org_id"] = session["user_id"]
    return jsonify(api_post("/campaigns", data))

@app.route("/api/campaigns/<int:campaign_id>/volunteers", methods=["GET"])
@require_login
def api_campaign_volunteers_list(campaign_id):
    return jsonify(api_get(f"/campaigns/{campaign_id}/volunteers") or [])

@app.route("/api/campaigns/<int:campaign_id>/volunteers", methods=["POST"])
@require_login
def api_campaign_volunteers_add(campaign_id):
    return jsonify(api_post(f"/campaigns/{campaign_id}/volunteers", request.json or {}))

@app.route("/api/campaigns/<int:campaign_id>/volunteers/<int:volunteer_id>", methods=["DELETE"])
@require_login
def api_campaign_volunteers_remove(campaign_id, volunteer_id):
    return jsonify(api_delete(f"/campaigns/{campaign_id}/volunteers/{volunteer_id}"))

@app.route("/api/campaigns/<int:campaign_id>", methods=["PUT"])
@require_login
def api_campaign_update(campaign_id):
    return jsonify(api_put(f"/campaigns/{campaign_id}", request.json or {}))

@app.route("/api/volunteers/available")
@require_login
def api_volunteers_available():
    return jsonify(api_get("/volunteers/available", dict(request.args)) or [])

@app.route("/api/volunteer/<int:user_id>/campaigns")
@require_login
def api_volunteer_campaigns(user_id):
    return jsonify(api_get(f"/volunteer/{user_id}/campaigns") or [])

@app.route("/api/volunteer/<int:user_id>/campaigns/pending")
@require_login
def api_volunteer_campaigns_pending(user_id):
    return jsonify(api_get(f"/volunteer/{user_id}/campaigns/pending") or {"count": 0})

@app.route("/api/campaign_volunteers/<int:cv_id>", methods=["PUT"])
@require_login
def api_campaign_volunteer_respond(cv_id):
    return jsonify(api_put(f"/campaign_volunteers/{cv_id}", request.json or {}))

@app.route("/api/chat", methods=["POST"])
@require_login
def api_chat():
    text = request.json.get("text", "")
    # Prepend volunteer profile context for richer agent matching
    if session.get("role") == "volunteer":
        db = get_db()
        u = db.execute("SELECT * FROM users WHERE id=?",
                       (session["user_id"],)).fetchone()
        db.close()
        if u:
            skills = json.loads(u["skills"] or "[]")
            avail  = "disponível" if u["available"] else "indisponível"
            ctx = (f"[Contexto do voluntário: nome={u['name']}, "
                   f"habilidades={', '.join(skills) or 'não especificadas'}, "
                   f"disponibilidade={avail}. "
                   f"Ajude-o a encontrar crises humanitárias onde possa contribuir.] ")
            text = ctx + text
    result = api_post("/chat", {"text": text, "user_id": session.get("user_id")})
    return jsonify(result)

# ── Run ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
