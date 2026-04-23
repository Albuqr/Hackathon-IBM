import os
import json
import sqlite3
from datetime import datetime
from ibm_watsonx_orchestrate.agent_builder.tools import tool


def get_db():
    path = os.environ.get("DB_PATH", "data/crisis.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


@tool
def analyze_distribution(min_severity: int = 3) -> str:
    """Analisa a distribuicao atual de voluntarios em missoes ativas.

    Identifica redundancias (mais voluntarios que o necessario),
    lacunas de cobertura (crises sem voluntarios suficientes) e
    calcula metricas de efetividade operacional do sistema.

    Args:
        min_severity: Severidade minima para incluir na analise. Padrao: 3.
    Returns:
        JSON string com redundancias, lacunas, cobertura e KPIs do sistema.
    """
    try:
        db = get_db()
        now = datetime.utcnow().isoformat()

        # Buscar crises ativas
        crises = db.execute("""
            SELECT id, title, country, severity, urgency, crisis_type,
                   people_affected, created_at
            FROM crises
            WHERE severity >= ?
            ORDER BY severity DESC
        """, (min_severity,)).fetchall()

        # Buscar matches ativos por crise
        matches = db.execute("""
            SELECT crisis_id, volunteer_id, status, score
            FROM matches
            WHERE status IN ('notified', 'confirmed', 'notified_whatsapp')
        """).fetchall()

        # Buscar total de voluntarios disponiveis
        total_volunteers = db.execute("""
            SELECT COUNT(*) as cnt FROM users
            WHERE role = 'volunteer' AND available = 1
        """).fetchone()["cnt"]

        # Buscar metricas de efetividade
        total_notified = db.execute("""
            SELECT COUNT(*) as cnt FROM matches
            WHERE status IN ('notified', 'notified_whatsapp')
        """).fetchone()["cnt"]

        total_confirmed = db.execute("""
            SELECT COUNT(*) as cnt FROM matches
            WHERE status = 'confirmed'
        """).fetchone()["cnt"]

        total_missions = db.execute("""
            SELECT COUNT(*) as cnt FROM missions
        """).fetchone()["cnt"]

        completed_missions = db.execute("""
            SELECT COUNT(*) as cnt FROM missions
            WHERE status = 'Concluida'
        """).fetchone()["cnt"]

        db.close()

        # Organizar matches por crise
        matches_by_crisis = {}
        for m in matches:
            cid = m["crisis_id"]
            if cid not in matches_by_crisis:
                matches_by_crisis[cid] = []
            matches_by_crisis[cid].append(dict(m))

        # Calcular necessidade estimada por severidade
        needed_map = {1: 2, 2: 5, 3: 10, 4: 25, 5: 50}

        redundancies = []
        gaps = []
        crises_list = []

        for crisis in crises:
            cid = crisis["id"]
            severity = int(crisis["severity"])
            needed = needed_map.get(severity, 10)
            current = len(matches_by_crisis.get(cid, []))
            confirmed = sum(
                1 for m in matches_by_crisis.get(cid, [])
                if m["status"] == "confirmed"
            )

            crises_list.append({
                "crisis_id": cid,
                "title": crisis["title"],
                "country": crisis["country"],
                "severity": severity,
                "urgency": crisis["urgency"],
                "volunteers_needed": needed,
                "volunteers_notified": current,
                "volunteers_confirmed": confirmed,
                "coverage_pct": round((confirmed / needed) * 100, 1)
                if needed > 0 else 0
            })

            # Detectar redundancia (>150% da capacidade)
            if current > needed * 1.5:
                redundancies.append({
                    "crisis_id": cid,
                    "title": crisis["title"],
                    "severity": severity,
                    "volunteers_current": current,
                    "volunteers_needed": needed,
                    "excess": current - needed,
                    "suggestion": "Realocar excesso para crises com lacunas"
                })

            # Detectar lacuna (severity >= 3 sem cobertura minima)
            if severity >= 3 and confirmed < needed * 0.5:
                gaps.append({
                    "crisis_id": cid,
                    "title": crisis["title"],
                    "country": crisis["country"],
                    "severity": severity,
                    "urgency": crisis["urgency"],
                    "volunteers_needed": needed,
                    "volunteers_confirmed": confirmed,
                    "shortage": needed - confirmed,
                    "priority": "CRITICA" if severity >= 4 else "ALTA"
                })

        # Calcular score global de cobertura
        total_needed = sum(c["volunteers_needed"] for c in crises_list)
        total_covered = sum(c["volunteers_confirmed"] for c in crises_list)
        coverage_score = round(total_covered / total_needed, 2) \
            if total_needed > 0 else 1.0

        # KPIs
        confirmation_rate = round(total_confirmed / total_notified, 2) \
            if total_notified > 0 else 0.0
        completion_rate = round(completed_missions / total_missions, 2) \
            if total_missions > 0 else 0.0

        # Alerta critico
        critical_alert = coverage_score < 0.5 or any(
            g["severity"] >= 5 for g in gaps
        )

        return json.dumps({
            "analysis_timestamp": now,
            "coverage_score": coverage_score,
            "critical_alert": critical_alert,
            "crises_analyzed": len(crises_list),
            "crises": crises_list,
            "redundancies": redundancies,
            "gaps": gaps,
            "summary": {
                "total_active_crises": len(crises),
                "total_volunteers_available": total_volunteers,
                "total_volunteers_notified": total_notified,
                "total_volunteers_confirmed": total_confirmed,
                "total_missions": total_missions,
                "completed_missions": completed_missions
            },
            "kpis": {
                "coverage_score": coverage_score,
                "confirmation_rate": confirmation_rate,
                "completion_rate": completion_rate,
                "critical_gaps": len([g for g in gaps if g["severity"] >= 4])
            }
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })