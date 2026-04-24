import os
import json
import asyncio
import sqlite3
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError
from ibm_watsonx_orchestrate.agent_builder.tools import tool

try:
    import httpx
except ImportError:
    httpx = None


def get_db():
    path = os.environ.get("DB_PATH", "data/crisis.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def format_urgency(urgency: str) -> str:
    map_ = {
        "immediate": "IMEDIATA",
        "24h": "24 horas",
        "48h": "48 horas",
        "7days": "7 dias",
        "monitoring": "Monitoramento"
    }
    return map_.get(urgency, urgency)


def format_severity(severity: int) -> str:
    map_ = {
        1: "Baixo",
        2: "Medio-Baixo",
        3: "Medio",
        4: "Alto",
        5: "CRITICO"
    }
    return map_.get(severity, str(severity))


def build_alert_message(volunteer_name: str, crisis: dict,
                        distance_km: float, skills: list) -> str:
    severity = int(crisis.get("severity", 1))
    urgency = crisis.get("urgency", "monitoring")
    title = crisis.get("title", "Crise sem titulo")
    country = crisis.get("country", "")
    affected = crisis.get("people_affected", 0)
    crisis_id = crisis.get("id", "")
    skills_str = ", ".join(skills) if skills else "geral"

    emoji_sev = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴", 5: "🚨"}.get(severity, "⚠️")

    message = (
        f"🛰️ *ALERTA DE CRISE — HKTN26*\n\n"
        f"{emoji_sev} *{title}*\n"
        f"🌍 País: {country}\n"
        f"⚠️ Severidade: {severity}/5 — {format_severity(severity)}\n"
        f"⏰ Urgência: {format_urgency(urgency)}\n"
        f"👥 Afetados: {affected:,}\n\n"
        f"Olá {volunteer_name}, suas habilidades em *{skills_str}* "
        f"são necessárias nesta missão.\n"
        f"📍 Você está a aproximadamente *{distance_km:.0f}km* da área afetada.\n\n"
        f"✅ Confirmar: /confirmar_{crisis_id}\n"
        f"❌ Recusar: /recusar_{crisis_id}\n\n"
        f"_Sistema HKTN26 — Hackathon IA Descomplicada_"
    )
    return message


async def send_message_async(token: str, chat_id: int, message: str) -> dict:
    try:
        bot = Bot(token=token)
        msg = await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="Markdown"
        )
        return {"success": True, "message_id": str(msg.message_id)}
    except TelegramError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def notify_telegram(matches_json: str, crisis_json: str) -> str:
    """Envia notificacoes de alerta de crise via Telegram para voluntarios.

    Args:
        matches_json: JSON string com lista de matches do match_volunteers.
        crisis_json: JSON string da crise com title, severity, urgency e country.
    Returns:
        JSON string com status de entrega de cada notificacao enviada.
    """
    try:
        token = os.environ.get("TG_TOKEN", "")
        if not token:
            return json.dumps({
                "status": "error",
                "message": "TG_TOKEN nao configurado no ambiente"
            })

        matches_data = json.loads(matches_json)
        crisis = json.loads(crisis_json)

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
            telegram_id = match.get("telegram_id")
            if not telegram_id:
                results.append({
                    "volunteer_id": match.get("volunteer_id"),
                    "name": match.get("name"),
                    "status": "skipped",
                    "reason": "sem telegram_id"
                })
                continue

            message = build_alert_message(
                volunteer_name=match.get("name", "Voluntario"),
                crisis=crisis,
                distance_km=float(match.get("distance_km", 0)),
                skills=match.get("skills", [])
            )

            # Registrar no banco ANTES de enviar
            try:
                db.execute("""
                    INSERT INTO matches
                    (crisis_id, volunteer_id, score, status, notified_at)
                    VALUES (?, ?, ?, 'pending', ?)
                """, (
                    crisis.get("id", ""),
                    match.get("volunteer_id"),
                    float(match.get("score", 0)),
                    now
                ))
                db.commit()
            except Exception:
                pass

            # Enviar mensagem
            send_result = asyncio.run(
                send_message_async(token, int(telegram_id), message)
            )

            # Atualizar status no banco
            if send_result["success"]:
                try:
                    db.execute("""
                        UPDATE matches SET status = 'notified'
                        WHERE crisis_id = ? AND volunteer_id = ?
                    """, (crisis.get("id", ""), match.get("volunteer_id")))
                    db.commit()
                except Exception:
                    pass

            results.append({
                "volunteer_id": match.get("volunteer_id"),
                "name": match.get("name"),
                "telegram_id": telegram_id,
                "status": "delivered" if send_result["success"] else "failed",
                "message_id": send_result.get("message_id"),
                "error": send_result.get("error"),
                "timestamp": now
            })

            # Rate limiting: 25 msg/s maximo
            asyncio.run(asyncio.sleep(0.04))

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


# ── Broadcast to country subscribers ─────────────────────────────────────────

def _sev_emoji(severity: int) -> str:
    return {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴", 5: "🚨"}.get(severity, "⚠️")


async def broadcast_to_subscribers(
    country: str,
    crisis_title: str,
    severity: int,
    map_url: str = ""
) -> dict:
    """Send a crisis alert to every Telegram subscriber for `country`.

    Queries telegram_subscribers, POSTs to the Telegram Bot API via httpx.
    One subscriber failure never stops the rest.
    Returns a summary dict with sent/failed counts.
    """
    token = os.environ.get("TG_TOKEN", "")
    if not token:
        print("[broadcast] TG_TOKEN not set — skipping broadcast")
        return {"sent": 0, "failed": 0, "reason": "no token"}

    if httpx is None:
        print("[broadcast] httpx not installed — skipping broadcast")
        return {"sent": 0, "failed": 0, "reason": "httpx not installed"}

    # Fetch subscribers
    db_path = os.environ.get("DB_PATH", "data/crisis.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT telegram_id, username FROM telegram_subscribers WHERE country = ?",
        (country,)
    ).fetchall()
    conn.close()

    if not rows:
        return {"sent": 0, "failed": 0, "reason": "no subscribers"}

    emoji = _sev_emoji(severity)
    text = (
        f"{emoji} *Alerta de Crise — HKTN26*\n\n"
        f"*{crisis_title}*\n"
        f"🌍 País: {country}\n"
        f"⚠️ Severidade: {severity}/5\n"
    )
    if map_url:
        text += f"\n🗺️ [Ver no mapa]({map_url})"
    text += "\n\n_Crisis Monitor — IA Humanitária_"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    sent = 0
    failed = 0

    async with httpx.AsyncClient(timeout=10) as client:
        for row in rows:
            try:
                resp = await client.post(url, json={
                    "chat_id": row["telegram_id"],
                    "text": text,
                    "parse_mode": "Markdown"
                })
                if resp.status_code == 200:
                    sent += 1
                else:
                    failed += 1
                    print(f"[broadcast] failed {row['telegram_id']}: {resp.text}")
            except Exception as e:
                failed += 1
                print(f"[broadcast] error {row['telegram_id']}: {e}")

    print(f"[broadcast] country={country} sent={sent} failed={failed}")
    return {"sent": sent, "failed": failed}