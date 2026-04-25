import os
import json
import requests
from datetime import datetime
from ibm_watsonx_orchestrate.agent_builder.tools import tool

VPS_API_URL = os.environ.get("VPS_API_URL", "http://31.97.83.21:17291")


@tool
def save_classification(event_json: str, classification_json: str) -> str:
    """Salva um evento de crise com sua classificacao via API do VPS.

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

        severity    = float(classification.get("severity", 1))
        urgency     = classification.get("urgency", "monitoring")
        crisis_type = classification.get("type", "humanitarian")

        payload = {
            "id":              crisis_id,
            "title":           event.get("title", ""),
            "country":         event.get("country", ""),
            "country_iso3":    event.get("country_iso3", "UNK"),
            "lat":             float(event.get("lat", 0)),
            "lon":             float(event.get("lon", 0)),
            "severity":        severity,
            "urgency":         urgency,
            "crisis_type":     crisis_type,
            "source":          event.get("source", "manual"),
            "people_affected": int(event.get("people_affected", 0)),
        }

        r = requests.post(
            f"{VPS_API_URL}/save_events",
            json=[payload],
            timeout=15
        )
        r.raise_for_status()
        result = r.json()

        return json.dumps({
            "status":     "ok",
            "crisis_id":  crisis_id,
            "severity":   severity,
            "urgency":    urgency,
            "saved":      result.get("saved", 0),
            "message":    f"Crise {crisis_id} enviada para o VPS com sucesso"
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status":    "error",
            "message":   str(e),
            "crisis_id": event.get("id", "unknown") if "event" in dir() else "unknown"
        })