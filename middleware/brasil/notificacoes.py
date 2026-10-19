"""Notificações do Dash Brasil (FR-035, CFG-005).

`BRASIL_NOTIFICACOES=fila` (padrão, enquanto o Telegram estiver fora): nada sai; cada mensagem vai para
`notificacoes_pendentes` e aparece para o admin. `enviar`: Telegram pela Bot API e WhatsApp pelo
`send_whatsapp_twilio` atual. As ferramentas `notify_*` não são chamadas porque gravam no banco do
Crisis (DB_PATH), o que quebraria o isolamento do brasil.db (FR-003).
"""
import os
from datetime import datetime, timezone

import requests

from . import db
from .config import Config

SEV_EMOJI = {1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴", 5: "🚨"}


def mensagem(nome: str, crise: dict, distancia_km: float) -> str:
    sev = int(round(crise.get("severity") or 1))
    return (f"🛰️ *ALERTA — Crisis Monitor Brasil*\n\n{SEV_EMOJI.get(sev, '⚠️')} *{crise.get('title', 'Crise')}*\n"
            f"Severidade {sev}/5 · {crise.get('uf') or 'Brasil'} · a {distancia_km:.0f} km de você\n\n"
            f"Olá, {nome}! Sua ajuda pode fazer diferença. Abra o Dash Brasil para se inscrever.")


def _enviar(canal: str, destino, texto: str) -> dict:
    if canal == "telegram":
        token = os.environ.get("TG_TOKEN", "")
        if not token or not destino:
            return {"ok": False, "erro": "sem TG_TOKEN ou sem telegram_id"}
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": destino, "text": texto, "parse_mode": "Markdown"}, timeout=15)
        return {"ok": r.ok, "erro": None if r.ok else r.text[:200]}
    import sys
    tools = os.path.join(os.path.dirname(__file__), "..", "..", "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from notify_whatsapp import send_whatsapp_twilio
    res = send_whatsapp_twilio(destino, texto)
    return {"ok": res.get("success", False), "erro": res.get("error")}


URGENCIA_TEXTO = {"baixa": "baixa", "media": "média", "alta": "alta", "critica": "crítica"}


def mensagem_convite(nome: str, org: str, campanha: dict, crise: dict, distancia_km: float | None) -> str:
    """Texto do convite de campanha; é o mesmo que a ONG vê na prévia antes de publicar."""
    perto = f", a {distancia_km:.0f} km de você" if distancia_km is not None else ""
    habs = ", ".join(campanha.get("skills_needed") or []) or "apoio geral"
    return (f"Olá, {nome}! A {org} convidou você para a campanha “{campanha.get('title', '')}”.\n"
            f"{crise.get('title', 'Crise')}{perto}. Urgência {URGENCIA_TEXTO.get(campanha.get('urgency'), campanha.get('urgency') or 'média')}.\n"
            f"Precisamos de: {habs}.\n"
            f"Responda em Minhas campanhas, no Crisis Monitor Brasil.")


def mensagem_encerramento(nome: str, org: str, campanha: dict) -> str:
    return (f"Olá, {nome}. A {org} encerrou a campanha “{campanha.get('title', '')}”. "
            f"Obrigado por ajudar.")


def _despachar(cfg: Config, conn, canais: list[str], v: dict, crisis_id, texto: str, rel: dict):
    for canal in canais:
        if cfg.notificacoes == "fila":
            conn.execute("INSERT INTO notificacoes_pendentes (canal, user_id, crisis_id, mensagem) VALUES (?,?,?,?)",
                         (canal, v["volunteer_id"], crisis_id, texto))
            rel["enfileiradas"] += 1
        else:
            destino = v.get("telegram_id") if canal == "telegram" else v.get("phone")
            res = _enviar(canal, destino, texto)
            rel["enviadas" if res["ok"] else "falhas"] += 1


def _canais(severidade) -> list[str]:
    return ["telegram"] + (["whatsapp"] if (severidade or 0) >= 4 else [])


def notificar(cfg: Config, crise: dict, matches: list[dict]) -> dict:
    """Notifica os voluntários do matching (Telegram; WhatsApp também se severidade ≥ 4)."""
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rel = {"modo": cfg.notificacoes, "enfileiradas": 0, "enviadas": 0, "falhas": 0}
    conn = db.conectar(cfg)
    try:
        for mt in matches:
            _despachar(cfg, conn, _canais(crise.get("severity")), mt, crise["id"], mensagem(mt["name"], crise, mt["distancia_km"]), rel)
            conn.execute("INSERT INTO matches (crisis_id, volunteer_id, score, status, notified_at) VALUES (?,?,?,?,?)",
                         (crise["id"], mt["volunteer_id"], mt["score"],
                          "na_fila" if cfg.notificacoes == "fila" else "notified", agora))
        conn.commit()
    finally:
        conn.close()
    return rel


def convidar(cfg: Config, conn, campanha: dict, crise: dict, org: str, voluntarios: list[dict]) -> dict:
    """Manda o convite da campanha a cada voluntário (volunteer_id, name, lat, lon, telegram_id, phone).
    Usa a conexão do chamador; quem chama faz o commit."""
    from .assistentes import haversine_km
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rel = {"modo": cfg.notificacoes, "enfileiradas": 0, "enviadas": 0, "falhas": 0}
    for v in voluntarios:
        km = haversine_km(crise["lat"], crise["lon"], v["lat"], v["lon"]) if v.get("lat") and crise.get("lat") is not None else None
        _despachar(cfg, conn, _canais(crise.get("severity")), v, crise.get("id"),
                   mensagem_convite(v["name"] or "voluntário", org, campanha, crise, km), rel)
        conn.execute("INSERT INTO matches (crisis_id, volunteer_id, score, status, notified_at) VALUES (?,?,?,?,?)",
                     (crise.get("id"), v["volunteer_id"], None, "convite", agora))
    return rel


def avisar_encerramento(cfg: Config, conn, campanha: dict, org: str, voluntarios: list[dict]) -> dict:
    rel = {"modo": cfg.notificacoes, "enfileiradas": 0, "enviadas": 0, "falhas": 0}
    for v in voluntarios:
        _despachar(cfg, conn, ["telegram"], v, campanha.get("crisis_id"), mensagem_encerramento(v["name"] or "voluntário", org, campanha), rel)
    return rel


def pendentes(cfg: Config, limite: int = 200) -> list[dict]:
    conn = db.conectar(cfg)
    try:
        return [dict(r) for r in conn.execute(
            """SELECT n.*, u.name AS nome FROM notificacoes_pendentes n LEFT JOIN users u ON u.id=n.user_id
               ORDER BY n.id DESC LIMIT ?""", (limite,))]
    finally:
        conn.close()
