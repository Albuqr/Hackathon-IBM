import os
import json
import sqlite3
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2
from ibm_watsonx_orchestrate.agent_builder.tools import tool


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


@tool
def suggest_reallocation(analysis_json: str) -> str:
    """Sugere realocacoes de voluntarios baseado na analise de distribuicao.

    Recebe o resultado do analyze_distribution e gera recomendacoes
    especificas de quais voluntarios realocar, de qual missao para qual,
    com justificativa e estimativa de ganho de impacto.

    Args:
        analysis_json: JSON string retornado pelo analyze_distribution.
    Returns:
        JSON string com lista de realocacoes sugeridas ordenadas por impacto.
    """
    try:
        analysis = json.loads(analysis_json)
        now = datetime.utcnow().isoformat()

        redundancies = analysis.get("redundancies", [])
        gaps = analysis.get("gaps", [])
        coverage_score = analysis.get("coverage_score", 1.0)

        if not gaps:
            return json.dumps({
                "status": "ok",
                "reallocations": [],
                "message": "Nenhuma lacuna de cobertura detectada. "
                           "Distribuicao adequada.",
                "coverage_score": coverage_score,
                "timestamp": now
            })

        if not redundancies:
            return json.dumps({
                "status": "ok",
                "reallocations": [],
                "message": "Lacunas detectadas mas sem redundancias para realocar. "
                           "Necessario recrutar novos voluntarios.",
                "gaps_count": len(gaps),
                "coverage_score": coverage_score,
                "timestamp": now
            })

        db = get_db()
        reallocations = []

        # Ordenar gaps por prioridade (severity DESC)
        gaps_sorted = sorted(gaps, key=lambda x: x["severity"], reverse=True)

        # Ordenar redundancias por excesso (maior excesso primeiro)
        redundancies_sorted = sorted(
            redundancies, key=lambda x: x["excess"], reverse=True
        )

        for gap in gaps_sorted:
            gap_crisis_id = gap["crisis_id"]
            shortage = gap["shortage"]

            # Buscar coordenadas da crise com lacuna
            gap_crisis = db.execute(
                "SELECT lat, lon, crisis_type FROM crises WHERE id = ?",
                (gap_crisis_id,)
            ).fetchone()

            if not gap_crisis:
                continue

            gap_lat = float(gap_crisis["lat"] or 0)
            gap_lon = float(gap_crisis["lon"] or 0)
            gap_type = gap_crisis["crisis_type"]

            for redundancy in redundancies_sorted:
                if shortage <= 0:
                    break

                red_crisis_id = redundancy["crisis_id"]
                excess = redundancy["excess"]

                if excess <= 0:
                    continue

                # Nao realocar entre crises de mesma severidade critica
                if gap["severity"] == redundancy["severity"] and \
                        gap["severity"] >= 4:
                    continue

                # Buscar voluntarios em excesso nessa crise
                excess_volunteers = db.execute("""
                    SELECT m.volunteer_id, m.score,
                           u.name, u.skills, u.lat, u.lon, u.telegram_id
                    FROM matches m
                    JOIN users u ON m.volunteer_id = u.id
                    WHERE m.crisis_id = ?
                    AND m.status IN ('notified', 'confirmed')
                    AND u.available = 1
                    ORDER BY m.score ASC
                    LIMIT ?
                """, (red_crisis_id, min(excess, shortage))).fetchall()

                for vol in excess_volunteers:
                    vol_lat = float(vol["lat"] or 0)
                    vol_lon = float(vol["lon"] or 0)
                    vol_skills = json.loads(vol["skills"] or "[]")

                    # Calcular distancia ate a crise com lacuna
                    if vol_lat == 0 or gap_lat == 0:
                        dist = 999
                    else:
                        dist = haversine_km(vol_lat, vol_lon, gap_lat, gap_lon)

                    # Verificar se voluntario esta dentro do raio aceitavel
                    max_dist = 1000 if gap["severity"] >= 4 else 500
                    if dist > max_dist:
                        continue

                    # Calcular ganho de impacto estimado
                    skill_match = gap_type in vol_skills
                    impact_gain = round(
                        (gap["severity"] / 5) * 0.4 +
                        (0.3 if skill_match else 0) +
                        max(0, (1 - dist / max_dist) * 0.3),
                        3
                    )

                    reallocations.append({
                        "volunteer_id": vol["volunteer_id"],
                        "volunteer_name": vol["name"],
                        "volunteer_skills": vol_skills,
                        "from_crisis_id": red_crisis_id,
                        "from_crisis_title": redundancy["title"],
                        "to_crisis_id": gap_crisis_id,
                        "to_crisis_title": gap["title"],
                        "to_crisis_severity": gap["severity"],
                        "to_crisis_urgency": gap["urgency"],
                        "distance_km": round(dist, 1),
                        "skill_match": skill_match,
                        "impact_gain": impact_gain,
                        "priority": "CRITICA" if gap["severity"] >= 4 else "ALTA",
                        "justification": (
                            f"{vol['name']} realocado de missao com excesso "
                            f"({redundancy['title']}) para crise {gap['severity']}/5 "
                            f"sem cobertura adequada ({gap['title']}). "
                            f"Distancia: {dist:.0f}km. "
                            f"Match de habilidades: {'Sim' if skill_match else 'Nao'}."
                        ),
                        "action_required": (
                            "Notificar voluntario sobre realocacao via Telegram"
                        )
                    })

                    shortage -= 1
                    redundancy["excess"] -= 1

        db.close()

        # Ordenar por impacto DESC
        reallocations.sort(key=lambda x: x["impact_gain"], reverse=True)

        # Estatisticas
        critical = [r for r in reallocations if r["priority"] == "CRITICA"]
        high = [r for r in reallocations if r["priority"] == "ALTA"]

        return json.dumps({
            "status": "ok",
            "reallocations": reallocations,
            "summary": {
                "total_reallocations": len(reallocations),
                "critical_priority": len(critical),
                "high_priority": len(high),
                "coverage_score_before": coverage_score,
                "estimated_coverage_after": min(
                    1.0,
                    coverage_score + len(reallocations) * 0.05
                )
            },
            "recommendation": (
                "Executar realocacoes criticas imediatamente" if critical
                else "Executar realocacoes de alta prioridade em breve"
                if high else "Nenhuma acao necessaria"
            ),
            "timestamp": now
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })