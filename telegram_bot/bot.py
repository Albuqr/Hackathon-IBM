import os
import sys
import math
import json
import logging
import requests
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes,
)

TG_TOKEN = os.environ.get("TG_TOKEN", "")
API_URL  = os.environ.get("API_URL", "http://middleware:8000")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory state — reset on restart
linked_users: dict[int, dict] = {}   # telegram_id -> user dict
alerted_ids:  set[str]        = set()  # crisis ids already alerted


# ── Helpers ────────────────────────────────────────────────────────────────

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_linked_user(telegram_id: int) -> dict | None:
    if telegram_id in linked_users:
        return linked_users[telegram_id]
    try:
        r = requests.get(f"{API_URL}/users/with-telegram", timeout=10)
        for u in r.json():
            if u.get("telegram_id") == telegram_id:
                linked_users[telegram_id] = u
                return u
    except Exception:
        pass
    return None


def parse_skills(raw) -> list[str]:
    if isinstance(raw, list):
        return raw
    try:
        return json.loads(raw or "[]")
    except Exception:
        return [raw] if raw else []


# ── Commands ───────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_linked_user(update.effective_user.id)
    if user:
        await update.message.reply_text(
            f"Olá, {user['name']}! Você já está conectado ao Crisis Monitor.\n"
            "Use /crises para ver crises ativas ou /meusdados para ver seu perfil."
        )
    else:
        await update.message.reply_text(
            "Bem-vindo ao Crisis Monitor Bot! 🌍\n\n"
            "Este bot envia alertas de crises humanitárias e permite que você se voluntarie diretamente pelo Telegram.\n\n"
            "Use /vincular SEU-CODIGO para conectar sua conta.\n"
            "Seu código está disponível no seu perfil no Crisis Monitor."
        )


async def cmd_vincular(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Use: /vincular SEU-CODIGO\nExemplo: /vincular AB12-CD34"
        )
        return

    code = context.args[0].upper().replace("-", "")
    try:
        r = requests.get(f"{API_URL}/user/by-code/{code}", timeout=10)
    except Exception:
        await update.message.reply_text("Erro ao conectar com o servidor. Tente novamente.")
        return

    if r.status_code == 404:
        await update.message.reply_text(
            "Código inválido. Verifique o código no seu perfil do Crisis Monitor."
        )
        return

    found = r.json()
    if found.get('role') != 'volunteer':
        await update.message.reply_text(
            "❌ Este bot é exclusivo para voluntários. ONGs devem acessar a plataforma pelo site."
        )
        return
    tg = update.effective_user
    try:
        requests.post(
            f"{API_URL}/user/{found['id']}/telegram",
            json={"telegram_id": tg.id, "username": tg.username or ""},
            timeout=10,
        )
    except Exception:
        pass

    linked_users[tg.id] = found
    roles_pt = {"volunteer": "Voluntário", "org": "ONG", "admin": "Admin"}
    role_label = roles_pt.get(found.get("role", ""), found.get("role", ""))
    await update.message.reply_text(
        f"✅ Conta vinculada com sucesso!\n"
        f"Olá, {found['name']}. Você está cadastrado como {role_label}."
    )


async def cmd_crises(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_linked_user(update.effective_user.id)
    if not user:
        await update.message.reply_text(
            "Você precisa vincular sua conta primeiro. Use /vincular SEU-CODIGO"
        )
        return
    if user.get('role') != 'volunteer':
        await update.message.reply_text(
            "❌ Este bot é exclusivo para voluntários. ONGs devem acessar a plataforma pelo site."
        )
        return

    try:
        r = requests.get(f"{API_URL}/events", params={"min_severity": 3, "limit": 5}, timeout=15)
        crises = r.json()
    except Exception:
        await update.message.reply_text("Erro ao buscar crises. Tente novamente.")
        return

    if not crises:
        await update.message.reply_text("Nenhuma crise ativa no momento.")
        return

    lines = ["🌍 *Crises ativas (top 5)*\n"]
    for c in crises[:5]:
        sev = int(c.get("severity") or 0)
        lines.append(
            f"*{c.get('title','?')}*\n"
            f"📍 {c.get('country','?')} | ⚠️ Severidade: {sev}/5 | Tipo: {c.get('crisis_type','?')}\n"
            f"ID: `{c.get('id','?')}`\n"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_meusdados(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_linked_user(update.effective_user.id)
    if not user:
        await update.message.reply_text(
            "Você precisa vincular sua conta primeiro. Use /vincular SEU-CODIGO"
        )
        return
    if user.get('role') != 'volunteer':
        await update.message.reply_text(
            "❌ Este bot é exclusivo para voluntários. ONGs devem acessar a plataforma pelo site."
        )
        return

    skills = parse_skills(user.get("skills"))
    skills_str = ", ".join(skills) if skills else "Não informadas"
    lat = user.get("lat") or 0
    lon = user.get("lon") or 0
    loc_str = f"{lat:.2f}, {lon:.2f}" if (lat or lon) else "Não definida"
    roles_pt = {"volunteer": "Voluntário", "org": "ONG", "admin": "Admin"}
    role_label = roles_pt.get(user.get("role", ""), user.get("role", ""))

    await update.message.reply_text(
        f"👤 *Seus dados*\n\n"
        f"Nome: {user.get('name','?')}\n"
        f"Função: {role_label}\n"
        f"Habilidades: {skills_str}\n"
        f"Localização: {loc_str}\n"
        f"Raio de atuação: {user.get('radius_km', 500)} km",
        parse_mode="Markdown",
    )


async def cmd_inscrever(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_linked_user(update.effective_user.id)
    if not user:
        await update.message.reply_text(
            "Você precisa vincular sua conta primeiro. Use /vincular SEU-CODIGO"
        )
        return
    if user.get('role') != 'volunteer':
        await update.message.reply_text(
            "❌ Este bot é exclusivo para voluntários. ONGs devem acessar a plataforma pelo site."
        )
        return

    if not context.args:
        await update.message.reply_text("Use: /inscrever {crisis_id}")
        return

    crisis_id = context.args[0]
    try:
        r = requests.post(
            f"{API_URL}/user/{user['id']}/associate-crisis",
            json={"crisis_id": crisis_id},
            timeout=10,
        )
        if r.status_code == 200:
            await update.message.reply_text("✅ Você foi inscrito na crise com sucesso!")
        else:
            await update.message.reply_text(
                "Erro ao se inscrever. Verifique o ID da crise e tente novamente."
            )
    except Exception:
        await update.message.reply_text("Erro ao conectar com o servidor. Tente novamente.")


# ── Free text ──────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_linked_user(update.effective_user.id)
    if not user:
        await update.message.reply_text(
            "Você precisa vincular sua conta primeiro. Use /vincular SEU-CODIGO"
        )
        return
    if user.get('role') != 'volunteer':
        await update.message.reply_text(
            "❌ Este bot é exclusivo para voluntários. ONGs devem acessar a plataforma pelo site."
        )
        return

    text = update.message.text
    context_type = "volunteer" if user.get("role") == "volunteer" else "assistant"
    await update.message.chat.send_action("typing")
    try:
        r = requests.post(
            f"{API_URL}/chat",
            json={"text": text, "context_type": context_type, "user_id": user["id"]},
            timeout=60,
        )
        data = r.json()
        reply = data.get("reply") or data.get("response") or "Sem resposta disponível."
        await update.message.reply_text(reply)
    except Exception:
        await update.message.reply_text("Erro ao conectar com o agente. Tente novamente.")


# ── Alert job ──────────────────────────────────────────────────────────────

async def alert_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        events = requests.get(
            f"{API_URL}/events", params={"min_severity": 4, "limit": 100}, timeout=15
        ).json()
        resp = requests.get(f"{API_URL}/users/with-telegram", timeout=10)
        users = resp.json()
    except Exception as e:
        logger.error(f"[alerts] fetch error: {e}")
        return

    if not isinstance(users, list):
        return

    for ev in events:
        ev_id = ev.get("id")
        if not ev_id or ev_id in alerted_ids:
            continue
        alerted_ids.add(ev_id)

        ev_lat = float(ev.get("lat") or 0)
        ev_lon = float(ev.get("lon") or 0)
        if ev_lat == 0 and ev_lon == 0:
            continue

        for u in users:
            if not isinstance(u, dict):
                continue
            tg_id = u.get("telegram_id")
            if not tg_id:
                continue
            u_lat = float(u.get("lat") or 0)
            u_lon = float(u.get("lon") or 0)
            if u_lat == 0 and u_lon == 0:
                continue
            radius = float(u.get("radius_km") or 500)
            dist = haversine_km(u_lat, u_lon, ev_lat, ev_lon)
            if dist > radius:
                continue

            try:
                msg = (
                    f"🚨 *ALERTA DE CRISE*\n"
                    f"{ev.get('title','?')}\n"
                    f"País: {ev.get('country','?')}\n"
                    f"Severidade: {int(ev.get('severity') or 0)}/5\n"
                    f"Tipo: {ev.get('crisis_type','?')}\n\n"
                    f"Esta crise está a {int(dist)} km de você.\n"
                    f"Use /inscrever {ev_id} para se voluntariar."
                )
                await context.bot.send_message(
                    chat_id=tg_id, text=msg, parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"[alerts] failed to notify {tg_id}: {e}")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    if not TG_TOKEN:
        logger.error("TG_TOKEN environment variable is not set — exiting.")
        sys.exit(1)

    application = Application.builder().token(TG_TOKEN).build()

    application.add_handler(CommandHandler("start",      cmd_start))
    application.add_handler(CommandHandler("vincular",   cmd_vincular))
    application.add_handler(CommandHandler("crises",     cmd_crises))
    application.add_handler(CommandHandler("meusdados",  cmd_meusdados))
    application.add_handler(CommandHandler("inscrever",  cmd_inscrever))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # Alert check every 30 minutes, first run after 60 seconds
    application.job_queue.run_repeating(alert_job, interval=1800, first=60)

    application.run_polling()


if __name__ == "__main__":
    main()
