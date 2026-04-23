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
def save_classification(event_json: str, classification_json: str) -> str:
    """Salva um evento de crise com sua classificacao no banco de dados.

    Args:
        event_json: JSON string do evento original coletado pelas tools de fetch.
        classification_json: JSON string da classificacao gerada pelo classify_crisis.
    Returns:
        JSON string com status, crisis_id e mensagem de confirmacao.
    """
    try:
        event = json.loads(event_json)
        classification = json.loads(classification_json)

        crisis_id = event.get("id", f"manual-{datetime.utcnow().timestamp()}")
        title = event.get("title", "")
        country = event.get("country", "")
        country_iso3 = event.get("country_iso3", "UNK")
        lat = float(event.get("lat", 0))
        lon = float(event.get("lon", 0))
        source = event.get("source", "manual")
        people_affected = int(event.get("people_affected", 0))
        url = event.get("url", "")

        severity = float(classification.get("severity", 1))
        urgency = classification.get("urgency", "monitoring")
        crisis_type = classification.get("type", "humanitarian")
        justification = classification.get("justification", "")
        confidence = float(classification.get("confidence", 0.5))
        needs_review = bool(classification.get("needs_review", False))
        trend = classification.get("trend", "stable")

        db = get_db()
        now = datetime.utcnow().isoformat()

        existing = db.execute(
            "SELECT id FROM crises WHERE id = ?", (crisis_id,)
        ).fetchone()

        if existing:
            db.execute("""
                UPDATE crises SET
                    severity = ?, urgency = ?, crisis_type = ?,
                    people_affected = ?, updated_at = ?
                WHERE id = ?
            """, (severity, urgency, crisis_type, people_affected, now, crisis_id))
            action = "updated"
        else:
            db.execute("""
                INSERT INTO crises (
                    id, title, country, country_iso3, lat, lon,
                    severity, urgency, crisis_type, source,
                    people_affected, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                crisis_id, title, country, country_iso3, lat, lon,
                severity, urgency, crisis_type, source,
                people_affected, now, now
            ))
            action = "created"

        db.execute("""
            CREATE TABLE IF NOT EXISTS classifications_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                crisis_id TEXT,
                severity REAL,
                urgency TEXT,
                crisis_type TEXT,
                confidence REAL,
                justification TEXT,
                needs_review BOOLEAN,
                trend TEXT,
                classified_at TEXT
            )
        """)
        db.execute("""
            INSERT INTO classifications_log (
                crisis_id, severity, urgency, crisis_type,
                confidence, justification, needs_review, trend, classified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            crisis_id, severity, urgency, crisis_type,
            confidence, justification, needs_review, trend, now
        ))

        db.commit()
        db.close()

        return json.dumps({
            "status": "ok",
            "action": action,
            "crisis_id": crisis_id,
            "severity": severity,
            "urgency": urgency,
            "needs_review": needs_review,
            "message": f"Crise {crisis_id} salva com sucesso ({action})"
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e),
            "crisis_id": event.get("id", "unknown") if "event" in dir() else "unknown"
        })