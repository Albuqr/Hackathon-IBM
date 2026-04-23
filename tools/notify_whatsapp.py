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


def format_whatsapp_message(volunteer_name: str, crisis: dict,
                             distance_km: float, skills: list) -> str:
    severity = int(crisis.get("severity", 1))
    title = crisis.get("title", "Crise sem titulo")
    country = crisis.get("country", "")
    urgency = crisis.get("urgency", "monitoring")
    crisis_id = crisis.get("id", "")
    skills_str = ", ".join(skills) if skills else "geral"

    urgency_map = {
        "immediate": "IMEDIATA",
        "24h": "24 horas",
        "48h": "48 horas",
        "7days": "7 dias",
        "monitoring": "Monitoramento"
    }

    message = (
        f"ALERTA HKTN26\n\n"
        f"Ola {volunteer_name},\n\n"
        f"CRISE: {title}\n"
        f"Pais: {country}\n"
        f"Severidade: {severity}/5\n"
        f"Urgencia: {urgency_map.get(urgency, urgency)}\n"
        f"Distancia: {distance_km:.0f}km de voce\n"
        f"Habilidades necessarias: {skills_str}\n\n"
        f"Responda SIM para confirmar disponibilidade.\n"
        f"Responda NAO se nao puder participar.\n\n"
        f"ID da missao: {crisis_id}\n"
        f"Sistema HKTN26 - Hackathon IA Descomplicada"
    )
    return message


def send_whatsapp_twilio(to_number: str, message: str) -> dict:
    try:
        from twilio.rest import Client
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        from_number = os.environ.get("TWILIO_WHATSAPP_NUMBER", "")

        if not all([account_sid, auth_token, from_number]):
            return {
                "success": False,
                "error": "Credenciais Twilio nao configuradas"
            }

        client = Client(account_sid, auth_token)
        msg = client.messages.create(
            from_=f"whatsapp:{from_number}",
            body=message,
            to=f"whatsapp:{to_number}"
        )
        return {"success": True, "message_sid": msg.sid}

    except ImportError:
        return {
            "success": False,
            "error": "Twilio nao instalado. Execute: pip install twilio"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def notify_whatsapp(matches_json: str, crisis_json: str) -> str:
    """Envia notificacoes de alerta de crise via WhatsApp usando Twilio.

    Args:
        matches_json: JSON string com lista de matches do match_volunteers.
        crisis_json: JSON string da crise com title, severity, urgency e country.
    Returns:
        JSON string com status de entrega de cada notificacao enviada.
    """
    try:
        matches_data = json.loads(matches_json)
        crisis = json.loads(crisis_json)
        severity = int(crisis.get("severity", 1))

        # WhatsApp apenas para severity >= 4
        if severity < 4:
            return json.dumps({
                "status": "skipped",
                "reason": f"Severity {severity} abaixo do minimo (4) para WhatsApp",
                "sent": 0
            })

        matches = matches_data if isinstance(matches_data, list) else \
            matches_data.get("matches", [])

        if not matches:
            return json.dumps({
                "status": "ok",
                "sent": 0,
                "message": "Nenhum match para notificar"
            })

        results = []
        db = get_db()
        now = datetime.utcnow().isoformat()

        for match in matches:
            phone = match.get("phone")
            if not phone:
                results.append({
                    "volunteer_id": match.get("volunteer_id"),
                    "name": match.get("name"),
                    "status": "skipped",
                    "reason": "sem numero de telefone"
                })
                continue

            # Normalizar numero
            phone = phone.strip().replace(" ", "").replace("-", "")
            if not phone.startswith("+"):
                phone = f"+55{phone}"

            message = format_whatsapp_message(
                volunteer_name=match.get("name", "Voluntario"),
                crisis=crisis,
                distance_km=float(match.get("distance_km", 0)),
                skills=match.get("skills", [])
            )

            # Registrar no banco antes de enviar
            try:
                db.execute("""
                    INSERT OR IGNORE INTO matches
                    (crisis_id, volunteer_id, score, status, notified_at)
                    VALUES (?, ?, ?, 'pending_whatsapp', ?)
                """, (
                    crisis.get("id", ""),
                    match.get("volunteer_id"),
                    float(match.get("score", 0)),
                    now
                ))
                db.commit()
            except Exception:
                pass

            send_result = send_whatsapp_twilio(phone, message)

            # Atualizar status
            if send_result["success"]:
                try:
                    db.execute("""
                        UPDATE matches SET status = 'notified_whatsapp'
                        WHERE crisis_id = ? AND volunteer_id = ?
                    """, (crisis.get("id", ""), match.get("volunteer_id")))
                    db.commit()
                except Exception:
                    pass

            results.append({
                "volunteer_id": match.get("volunteer_id"),
                "name": match.get("name"),
                "phone": phone,
                "status": "delivered" if send_result["success"] else "failed",
                "message_sid": send_result.get("message_sid"),
                "error": send_result.get("error"),
                "timestamp": now
            })

            # Rate limit Twilio sandbox: 1 msg/s
            import time
            time.sleep(1)

        db.close()

        delivered = sum(1 for r in results if r["status"] == "delivered")
        failed = sum(1 for r in results if r["status"] == "failed")
        skipped = sum(1 for r in results if r["status"] == "skipped")

        return json.dumps({
            "status": "ok",
            "results": results,
            "summary": {
                "total": len(results),
                "delivered": delivered,
                "failed": failed,
                "skipped": skipped
            },
            "timestamp": now
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        })