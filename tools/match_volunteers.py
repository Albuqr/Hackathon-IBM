import os
import json
import sqlite3
import numpy as np
from math import radians, sin, cos, sqrt, atan2
from datetime import datetime
from ibm_watsonx_ai import Credentials, APIClient
from ibm_watsonx_ai.foundation_models import Embeddings
from ibm_watsonx_orchestrate.agent_builder.tools import tool

_embedder = None


def get_db():
    path = os.environ.get("DB_PATH", "data/crisis.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def cosine_sim(a, b):
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def get_embedder():
    global _embedder
    if not _embedder:
        api = APIClient(
            Credentials(
                url="https://us-south.ml.cloud.ibm.com",
                api_key=os.environ["WATSONX_APIKEY"]
            ),
            project_id=os.environ["WATSONX_PROJECT_ID"]
        )
        _embedder = Embeddings(
            model_id="ibm/granite-embedding-278m-multilingual",
            api_client=api
        )
    return _embedder


@tool
def match_volunteers(crisis_json: str, top_n: int = 5) -> str:
    """Encontra os voluntarios mais compativeis para uma crise usando embeddings.

    Args:
        crisis_json: JSON string da crise com lat, lon, type, severity e title.
        top_n: Numero maximo de voluntarios a retornar. Padrao: 5.
    Returns:
        JSON string com lista rankeada de voluntarios por score de compatibilidade.
    """
    try:
        crisis = json.loads(crisis_json)
        severity = int(crisis.get("severity", 1))
        crisis_type = crisis.get("type", "")
        crisis_title = crisis.get("title", "")
        crisis_lat = float(crisis.get("lat", 0))
        crisis_lon = float(crisis.get("lon", 0))
        crisis_country = crisis.get("country_iso3", "")

        # Expandir raio para emergencias criticas
        radius_multiplier = 3.0 if severity == 5 else 1.0

        db = get_db()
        volunteers = db.execute("""
            SELECT id, name, skills, languages, lat, lon,
                   radius_km, telegram_id, phone
            FROM users
            WHERE role = 'volunteer'
            AND available = 1
        """).fetchall()
        db.close()

        if not volunteers:
            return json.dumps({
                "matches": [],
                "total_eligible": 0,
                "message": "Nenhum voluntario disponivel no momento"
            })

        # Gerar embedding da crise
        query = f"{crisis_type} severity {severity}: {crisis_title}"
        embedder = get_embedder()
        crisis_emb = embedder.embed_query(query)

        # Carregar embeddings pre-computados se existirem
        emb_path = os.environ.get("VOL_EMBEDDINGS_PATH", "data/volunteer_embeddings.npy")
        vol_embs = None
        if os.path.exists(emb_path):
            vol_embs = np.load(emb_path)

        scored = []
        for i, vol in enumerate(volunteers):
            vol_lat = float(vol["lat"] or 0)
            vol_lon = float(vol["lon"] or 0)
            vol_radius = float(vol["radius_km"] or 500) * radius_multiplier

            # Filtro geografico
            if vol_lat == 0 and vol_lon == 0:
                dist = 0
            else:
                dist = haversine_km(crisis_lat, crisis_lon, vol_lat, vol_lon)
                if dist > vol_radius:
                    continue

            # Similaridade semantica
            skills = json.loads(vol["skills"] or "[]")
            languages = json.loads(vol["languages"] or "[]")
            vol_profile = f"{' '.join(skills)} {' '.join(languages)}"

            if vol_embs is not None and i < len(vol_embs):
                vol_emb = vol_embs[i]
            else:
                vol_emb = embedder.embed_query(vol_profile)

            sim = cosine_sim(crisis_emb, vol_emb)

            # Bonus por compatibilidade
            bonus = 0.0
            if crisis_type in skills:
                bonus += 0.15
            if crisis_country.lower() in [l.lower() for l in languages]:
                bonus += 0.08
            if dist < vol_radius * 0.2:
                bonus += 0.10

            # Penalidade para voluntarios ja notificados recentemente
            db2 = get_db()
            recent = db2.execute("""
                SELECT COUNT(*) as cnt FROM matches
                WHERE volunteer_id = ?
                AND notified_at > datetime('now', '-30 minutes')
            """, (vol["id"],)).fetchone()
            db2.close()
            if recent and recent["cnt"] > 0:
                bonus -= 0.10

            final_score = round(sim * 0.6 + bonus, 4)

            scored.append({
                "volunteer_id": vol["id"],
                "name": vol["name"],
                "score": final_score,
                "distance_km": round(dist, 1),
                "skills": skills,
                "languages": languages,
                "telegram_id": vol["telegram_id"],
                "phone": vol["phone"],
                "justification": (
                    f"Score {final_score:.2f} — "
                    f"distancia {dist:.0f}km, "
                    f"habilidades: {', '.join(skills)}"
                )
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[:top_n] if severity < 5 else scored[:10]

        return json.dumps({
            "crisis_id": crisis.get("id", ""),
            "matches": top,
            "total_eligible": len(scored),
            "top_n_returned": len(top),
            "algorithm": "hybrid_embedding_v1",
            "timestamp": datetime.utcnow().isoformat()
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "matches": [],
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })