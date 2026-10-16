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


def notificar(cfg: Config, crise: dict, matches: list[dict]) -> dict:
    """Notifica os voluntários do matching (Telegram; WhatsApp também se severidade ≥ 4)."""
    agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    canais = ["telegram"] + (["whatsapp"] if (crise.get("severity") or 0) >= 4 else [])
    rel = {"modo": cfg.notificacoes, "enfileiradas": 0, "enviadas": 0, "falhas": 0}
    conn = db.conectar(cfg)
    try:
        for mt in matches:
            texto = mensagem(mt["name"], crise, mt["distancia_km"])
            for canal in canais:
                if cfg.notificacoes == "fila":
                    conn.execute("INSERT INTO notificacoes_pendentes (canal, user_id, crisis_id, mensagem) VALUES (?,?,?,?)",
                                 (canal, mt["volunteer_id"], crise["id"], texto))
                    rel["enfileiradas"] += 1
                else:
                    destino = mt.get("telegram_id") if canal == "telegram" else mt.get("phone")
                    res = _enviar(canal, destino, texto)
                    rel["enviadas" if res["ok"] else "falhas"] += 1
            conn.execute("INSERT INTO matches (crisis_id, volunteer_id, score, status, notified_at) VALUES (?,?,?,?,?)",
                         (crise["id"], mt["volunteer_id"], mt["score"],
                          "na_fila" if cfg.notificacoes == "fila" else "notified", agora))
        conn.commit()
    finally:
        conn.close()
    return rel


def pendentes(cfg: Config, limite: int = 200) -> list[dict]:
    conn = db.conectar(cfg)
    try:
        return [dict(r) for r in conn.execute(
            """SELECT n.*, u.name AS nome FROM notificacoes_pendentes n LEFT JOIN users u ON u.id=n.user_id
               ORDER BY n.id DESC LIMIT ?""", (limite,))]
    finally:
        conn.close()
