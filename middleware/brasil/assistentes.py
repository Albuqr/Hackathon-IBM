"""Regras determinísticas do Dash Brasil usadas pelo provedor `local` e como dados de contexto
para os provedores com LLM (FR-030–FR-034)."""
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import db, malha
from .config import Config

# Habilidades úteis por tipo de crise (para recomendação e matching sem embeddings)
HABILIDADES_POR_TIPO = {
    "wildfire": {"combate a incêndio", "brigadista", "primeiros socorros", "logística", "saúde"},
    "meteorological": {"resgate", "primeiros socorros", "logística", "abrigo", "saúde", "engenharia"},
    "geological": {"resgate", "engenharia", "primeiros socorros", "logística", "abrigo"},
    "hydrological": {"resgate", "abrigo", "logística", "primeiros socorros", "saúde"},
    "drought": {"logística", "distribuição de água", "saúde", "assistência social"},
    "sanitary": {"saúde", "enfermagem", "medicina", "logística", "comunicação"},
    "seismic": {"resgate", "engenharia", "primeiros socorros", "logística"},
    "humanitarian": {"assistência social", "logística", "saúde", "abrigo", "comunicação"},
    "conflict": {"assistência social", "saúde", "comunicação"},
}
NOMES_TIPO = {"wildfire": "queimada", "meteorological": "evento meteorológico", "geological": "evento geológico",
              "hydrological": "evento hidrológico",
              "drought": "seca", "sanitary": "crise sanitária", "seismic": "sismo", "humanitarian": "crise humanitária",
              "conflict": "conflito"}
URGENCIA_POR_SEV = {5: "crítica", 4: "alta", 3: "média", 2: "baixa", 1: "baixa"}
VOLUNTARIOS_POR_SEV = {5: 40, 4: 20, 3: 10, 2: 5, 1: 3}


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _norm(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s.lower().strip()) if unicodedata.category(c) != "Mn")


def compativel(skills: list[str], tipo: str) -> set[str]:
    uteis = {_norm(h) for h in HABILIDADES_POR_TIPO.get(tipo, set())}
    return {s for s in skills if _norm(s) in uteis}


def _ativas(conn, agora):
    return [dict(r) for r in conn.execute(
        """SELECT * FROM crises WHERE (expira_em IS NULL OR expira_em > ?) AND verificacao != 'descartada'""",
        (agora.isoformat(timespec="seconds"),))]


# ── FR-030: recomendações para o voluntário ───────────────────────────
def recomendar(cfg: Config, user_id: int, limite: int = 10, agora=None) -> dict:
    agora = agora or datetime.now(timezone.utc)
    conn = db.conectar(cfg)
    try:
        u = dict(conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())
        skills = json.loads(u.get("skills") or "[]")
        crises = _ativas(conn, agora)
    finally:
        conn.close()
    cands = []
    for c in crises:
        uteis = compativel(skills, c["crisis_type"])
        if skills and not uteis:
            continue
        d = haversine_km(u["lat"], u["lon"], c["lat"], c["lon"])
        cands.append({"id": c["id"], "title": c["title"], "severity": c["severity"], "crisis_type": c["crisis_type"],
                      "uf": c["uf"], "distancia_km": round(d, 1), "habilidades_uteis": sorted(uteis)})
    cands.sort(key=lambda x: x["distancia_km"])
    return {"usuario": {"nome": u["name"], "habilidades": skills, "lat": u["lat"], "lon": u["lon"],
                        "raio_km": u["radius_km"]}, "crises": cands[:limite]}


def texto_recomendacao(ctx: dict) -> str:
    if not ctx["crises"]:
        return ("Não encontrei crises ativas no Brasil compatíveis com suas habilidades agora. "
                "Atualize suas habilidades no perfil ou volte mais tarde.")
    linhas = [f"Encontrei {len(ctx['crises'])} crises ativas perto de você onde suas habilidades ajudam:"]
    for c in ctx["crises"]:
        uteis = f" — útil: {', '.join(c['habilidades_uteis'])}" if c["habilidades_uteis"] else ""
        linhas.append(f"• {c['title']} ({c['uf'] or 'BR'}, severidade {int(c['severity'])}, {c['distancia_km']:.0f} km){uteis}")
    linhas.append("Abra a crise no mapa e clique em \"Quero ajudar\" para se inscrever.")
    return "\n".join(linhas)


# ── FR-031: plano de campanha para a ONG ──────────────────────────────
def plano_campanha(cfg: Config, crisis_id: str) -> dict:
    conn = db.conectar(cfg)
    try:
        c = conn.execute("SELECT * FROM crises WHERE id=?", (crisis_id,)).fetchone()
    finally:
        conn.close()
    if not c:
        return {}
    c = dict(c)
    sev = int(round(c["severity"]))
    info = malha.carregar().info(c["municipio_ibge"]) if c["municipio_ibge"] else None
    local = f"{info['nome']} ({info['uf']})" if info else (c["uf"] or "Brasil")
    tipo = NOMES_TIPO.get(c["crisis_type"], c["crisis_type"])
    return {
        "crise": {"id": c["id"], "title": c["title"], "severity": sev, "local": local},
        "resumo": f"{tipo.capitalize()} em {local}, severidade {sev} de 5 ({c['source'].upper()}).",
        "habilidades": sorted(HABILIDADES_POR_TIPO.get(c["crisis_type"], {"logística"})),
        "voluntarios": VOLUNTARIOS_POR_SEV.get(sev, 5),
        "urgencia": URGENCIA_POR_SEV.get(sev, "média"),
        "descricao": (f"Campanha de apoio à {tipo} em {local}. Buscamos voluntários para atuar presencialmente "
                      f"ou na retaguarda, em turnos combinados com a coordenação local e a Defesa Civil."),
    }


def texto_plano(p: dict) -> str:
    if not p:
        return "Escolha uma crise do mapa para eu montar o plano da campanha."
    return (f"Resumo da necessidade: {p['resumo']}\n"
            f"Habilidades necessárias: {', '.join(p['habilidades'])}\n"
            f"Número de voluntários recomendado: {p['voluntarios']}\n"
            f"Urgência: {p['urgencia']}\n"
            f"Descrição da campanha: {p['descricao']}")


# ── FR-032: matching ──────────────────────────────────────────────────
def matching(cfg: Config, crisis_id: str, limite: int = 20, agora=None, habilidades: list[str] | None = None) -> list[dict]:
    """Algoritmo do matching_agent atual, sem embeddings: raio, sobreposição de habilidades e bônus.

    `habilidades` troca as do tipo da crise pelas do plano da campanha. Cada resultado traz os motivos do score."""
    agora = agora or datetime.now(timezone.utc)
    m = malha.carregar()
    conn = db.conectar(cfg)
    try:
        c = conn.execute("SELECT * FROM crises WHERE id=?", (crisis_id,)).fetchone()
        if not c:
            return []
        vols = [dict(r) for r in conn.execute("SELECT * FROM users WHERE role='volunteer' AND available=1")]
        historico = {r[0] for r in conn.execute("SELECT DISTINCT volunteer_id FROM campaign_volunteers WHERE status='confirmed'")}
        recentes = {r[0] for r in conn.execute("SELECT volunteer_id FROM matches WHERE notified_at > ?",
                                                ((agora - timedelta(hours=24)).isoformat(),))}
    finally:
        conn.close()
    sev = int(round(c["severity"]))
    precisa = {_norm(h) for h in (habilidades if habilidades else HABILIDADES_POR_TIPO.get(c["crisis_type"], set()))}
    out = []
    for v in vols:
        if not v["lat"] or not m.no_brasil(v["lat"], v["lon"]):
            continue  # só voluntários no Brasil
        d = haversine_km(c["lat"], c["lon"], v["lat"], v["lon"])
        raio = (v["radius_km"] or 500) * (3 if sev >= 5 else 1)
        if d > raio:
            continue
        originais = json.loads(v["skills"] or "[]")
        skills = {_norm(s) for s in originais}
        sim = len(skills & precisa) / len(precisa | skills) if (skills or precisa) else 0
        score = 0.5 * sim
        score += 0.15 if skills & precisa else 0
        score += 0.10 if v["id"] in historico else 0
        score += 0.08 if any(_norm(l) in ("portugues", "pt", "pt-br") for l in json.loads(v["languages"] or "[]")) else 0
        score += 0.10 if d <= 50 else 0
        score -= 0.10 if v["id"] in recentes else 0
        out.append({"volunteer_id": v["id"], "name": v["name"], "distancia_km": round(d, 1),
                    "score": round(max(0.0, min(1.0, score)), 3), "telegram_id": v["telegram_id"], "phone": v["phone"],
                    "skills": originais, "habilidades_comuns": sorted(s for s in originais if _norm(s) in precisa),
                    "historico": v["id"] in historico, "avisado_24h": v["id"] in recentes})
    out.sort(key=lambda x: (-x["score"], x["distancia_km"]))
    return out[: max(limite, 10) if sev >= 5 else limite]


# ── acompanhamento da campanha: cobertura e próximo passo (regras, sem IA) ──
def cobertura(habilidades: list[str], pessoas: list[dict]) -> list[dict]:
    """Quantas pessoas da campanha têm cada habilidade do plano. Sem meta por habilidade: só mostra o que está descoberto."""
    out = []
    for h in habilidades:
        n = _norm(h)
        tem = [p for p in pessoas if n in {_norm(s) for s in p.get("skills") or []}]
        out.append({"habilidade": h, "confirmados": sum(p["status"] == "confirmed" for p in tem),
                    "aguardando": sum(p["status"] == "selected" for p in tem)})
    return out


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def proximo_passo(s: dict) -> dict:
    """O único próximo passo da campanha, nesta ordem: crise saiu › agravou › faltam pessoas › sem resposta › completa › aguardar.

    `s`: crise_ativa, sev_atual, sev_inicio (ou None), meta, confirmados, aguardando,
    sem_resposta [{volunteer_id, name}], recomendados [{volunteer_id, ...}], descobertas [habilidade]."""
    meta, conf, agu = s["meta"], s["confirmados"], s["aguardando"]
    if not s["crise_ativa"]:
        return {"tipo": "crise_saiu", "titulo": "A crise saiu do mapa.",
                "texto": "O alerta expirou ou foi descartado. Se a ação também terminou, encerre a campanha.", "acao": "encerrar"}
    sugerida = VOLUNTARIOS_POR_SEV.get(s["sev_atual"], 5)
    if s.get("sev_inicio") is not None and s["sev_atual"] > s["sev_inicio"] and sugerida > meta:
        return {"tipo": "agravou", "titulo": "A crise agravou.",
                "texto": f"A severidade subiu de {s['sev_inicio']} para {s['sev_atual']}. "
                         f"O assistente sugere aumentar a meta de {meta} para {sugerida} pessoas.",
                "acao": "aumentar_meta", "meta_sugerida": sugerida}
    faltam = meta - conf - agu
    if faltam > 0:
        recs = s["recomendados"][:faltam]
        foco = f"Sem ninguém para {', '.join(s['descobertas'])}. " if s["descobertas"] else ""
        if recs:
            return {"tipo": "faltam", "titulo": f"Faltam {_plural(faltam, 'pessoa', 'pessoas')}.",
                    "texto": f"{foco}O assistente achou {_plural(len(recs), 'pessoa compatível', 'pessoas compatíveis')} "
                             f"que ainda não {'foi convidada' if len(recs) == 1 else 'foram convidadas'}.",
                    "acao": "convidar", "volunteer_ids": [r["volunteer_id"] for r in recs]}
        return {"tipo": "faltam", "titulo": f"Faltam {_plural(faltam, 'pessoa', 'pessoas')}.",
                "texto": f"{foco}Não há mais voluntários compatíveis no raio da crise. Busque outra pessoa pelo nome ou habilidade.",
                "acao": "buscar"}
    if s["sem_resposta"]:
        n = len(s["sem_resposta"])
        nomes = ", ".join(p["name"] for p in s["sem_resposta"][:3]) + (" e outras" if n > 3 else "")
        return {"tipo": "sem_resposta", "titulo": f"{_plural(n, 'convite', 'convites')} sem resposta há mais de 24 h.",
                "texto": f"{nomes} ainda não {'respondeu' if n == 1 else 'responderam'}.",
                "acao": "reenviar", "volunteer_ids": [p["volunteer_id"] for p in s["sem_resposta"]]}
    if conf >= meta:
        return {"tipo": "completa", "titulo": "Equipe completa.",
                "texto": f"{conf} de {meta} pessoas confirmadas. Encerre a campanha quando a ação terminar.", "acao": "encerrar"}
    return {"tipo": "aguardar", "titulo": f"Aguardando {_plural(agu, 'resposta', 'respostas')}.",
            "texto": "Os convites saíram há menos de 24 h. Se ninguém responder até lá, você poderá reenviar.", "acao": None}


def situacao_campanha(cfg: Config, cid: int, agora=None) -> dict:
    agora = agora or datetime.now(timezone.utc)
    conn = db.conectar(cfg)
    try:
        cam = dict(conn.execute("SELECT * FROM campaigns WHERE id=?", (cid,)).fetchone())
        crise = conn.execute("SELECT * FROM crises WHERE id=?", (cam["crisis_id"],)).fetchone()
        ativa = bool(crise) and crise["verificacao"] != "descartada" and (
            not crise["expira_em"] or crise["expira_em"] > agora.isoformat(timespec="seconds"))
        inicio = conn.execute("""SELECT severity FROM classifications_log WHERE crisis_id=? AND classified_at <= ?
                                 ORDER BY classified_at DESC LIMIT 1""", (cam["crisis_id"], cam["created_at"])).fetchone()
        pessoas = [dict(r) | {"skills": json.loads(r["skills"] or "[]")} for r in conn.execute(
            """SELECT cv.volunteer_id, cv.status, cv.added_at, u.name, u.skills FROM campaign_volunteers cv
               JOIN users u ON u.id=cv.volunteer_id WHERE cv.campaign_id=? AND cv.status != 'removed'""", (cid,))]
    finally:
        conn.close()
    habilidades = json.loads(cam["skills_needed"] or "[]")
    cob = cobertura(habilidades, pessoas)
    descobertas = [c["habilidade"] for c in cob if not c["confirmados"] and not c["aguardando"]]
    limite = agora - timedelta(hours=24)

    def antigo(p):
        try:
            d = datetime.fromisoformat(str(p["added_at"]).replace("Z", "+00:00"))
        except ValueError:
            return False
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)) < limite

    sem_resposta = [{"volunteer_id": p["volunteer_id"], "name": p["name"]} for p in pessoas if p["status"] == "selected" and antigo(p)]
    ja = {p["volunteer_id"] for p in pessoas}
    recomendados = []
    if ativa and cam["status"] == "active":
        cands = [r for r in matching(cfg, cam["crisis_id"], 60, agora, habilidades or None) if r["volunteer_id"] not in ja]
        alvo = {_norm(h) for h in descobertas}
        cands.sort(key=lambda r: (-bool({_norm(x) for x in r["habilidades_comuns"]} & alvo), -r["score"], r["distancia_km"]))
        recomendados = [{k: r[k] for k in ("volunteer_id", "name", "distancia_km", "score", "habilidades_comuns", "historico",
                                           "avisado_24h")} for r in cands[:10]]
    conta = {st: sum(p["status"] == st for p in pessoas) for st in ("selected", "confirmed", "declined")}
    s = {"crise_ativa": ativa, "sev_atual": int(round(crise["severity"])) if crise else 0,
         "sev_inicio": int(round(inicio["severity"])) if inicio and inicio["severity"] is not None else None,
         "meta": cam["target_volunteers"], "confirmados": conta["confirmed"], "aguardando": conta["selected"],
         "sem_resposta": sem_resposta, "recomendados": recomendados, "descobertas": descobertas}
    passo = proximo_passo(s) if cam["status"] == "active" else {
        "tipo": "encerrada", "titulo": "Campanha encerrada.", "texto": "Ela não recebe mais convites.", "acao": None}
    return {"crise": {"ativa": ativa, "severidade": s["sev_atual"], "severidade_inicio": s["sev_inicio"]},
            "funil": {"meta": cam["target_volunteers"], "convidados": sum(conta.values()), "confirmados": conta["confirmed"],
                      "aguardando": conta["selected"], "recusaram": conta["declined"], "sem_resposta": len(sem_resposta)},
            "cobertura": cob, "recomendados": recomendados, "proximo_passo": passo, "canal": cfg.notificacoes}


# ── FR-033: distribuição e realocação ─────────────────────────────────
def distribuicao(cfg: Config, agora=None) -> dict:
    agora = agora or datetime.now(timezone.utc)
    conn = db.conectar(cfg)
    try:
        crises = {c["id"]: c for c in _ativas(conn, agora)}
        alocados = defaultdict(set)
        for r in conn.execute("""SELECT cam.crisis_id, cv.volunteer_id FROM campaign_volunteers cv
                                 JOIN campaigns cam ON cam.id=cv.campaign_id
                                 WHERE cv.status IN ('selected','confirmed') AND cam.status='active'"""):
            alocados[r[0]].add(r[1])
        for r in conn.execute("SELECT crisis_id, user_id FROM crisis_associations WHERE role='volunteer'"):
            alocados[r[0]].add(r[1])
        metas = defaultdict(int)
        for r in conn.execute("SELECT crisis_id, target_volunteers FROM campaigns WHERE status='active'"):
            metas[r[0]] += r[1] or 0
    finally:
        conn.close()
    redundancias, lacunas = [], []
    for cid, c in crises.items():
        sev = int(round(c["severity"]))
        meta = metas.get(cid) or VOLUNTARIOS_POR_SEV.get(sev, 5)
        n = len(alocados.get(cid, ()))
        if n > 1.5 * meta:
            redundancias.append({"crisis_id": cid, "title": c["title"], "voluntarios": n, "meta": meta,
                                 "excedente": n - meta, "lat": c["lat"], "lon": c["lon"]})
        elif sev >= 3 and n < max(1, meta // 2) and (cid in metas or sev >= 4):
            lacunas.append({"crisis_id": cid, "title": c["title"], "severity": sev, "voluntarios": n, "meta": meta,
                            "crisis_type": c["crisis_type"], "uf": c["uf"], "verificacao": c["verificacao"],
                            "faltam": meta - n, "lat": c["lat"], "lon": c["lon"]})
    lacunas.sort(key=lambda x: (-x["severity"], -x["faltam"]))
    sugestoes = []
    for r in sorted(redundancias, key=lambda x: -x["excedente"]):
        sobra = r["excedente"]
        for l in sorted(lacunas, key=lambda x: haversine_km(r["lat"], r["lon"], x["lat"], x["lon"])):
            if sobra <= 0:
                break
            mover = min(sobra, l["faltam"])
            if mover <= 0:
                continue
            sugestoes.append({"de": r["crisis_id"], "para": l["crisis_id"], "voluntarios": mover,
                              "distancia_km": round(haversine_km(r["lat"], r["lon"], l["lat"], l["lon"])),
                              "texto": f"Mover {mover} voluntário(s) de \"{r['title']}\" para \"{l['title']}\""})
            l["faltam"] -= mover
            sobra -= mover
    cobertas = sum(1 for cid in crises if alocados.get(cid))
    return {"redundancias": redundancias, "lacunas": lacunas[:50], "sugestoes": sugestoes,
            "cobertura": round(cobertas / len(crises), 3) if crises else 1.0}


# ── FR-034: previsões por recorrência ─────────────────────────────────
def previsoes(cfg: Config, agora=None, minimo_dias: int = 3) -> list[dict]:
    """Municípios com crises do mesmo tipo em pelo menos `minimo_dias` dias dos últimos 30."""
    agora = agora or datetime.now(timezone.utc)
    desde = (agora - timedelta(days=30)).isoformat()
    conn = db.conectar(cfg)
    try:
        linhas = conn.execute(
            """SELECT c.municipio_ibge, l.crisis_type, COUNT(DISTINCT substr(l.classified_at,1,10)) AS dias,
                      MAX(l.severity) AS sev_max
               FROM classifications_log l JOIN crises c ON c.id=l.crisis_id
               WHERE l.classified_at >= ? AND c.municipio_ibge IS NOT NULL
               GROUP BY c.municipio_ibge, l.crisis_type HAVING dias >= ? ORDER BY dias DESC, sev_max DESC LIMIT 30""",
            (desde, minimo_dias)).fetchall()
    finally:
        conn.close()
    m = malha.carregar()
    out = []
    for cod, tipo, dias, sev in linhas:
        info = m.info(cod) or {}
        prob = "alta" if dias >= 10 else "média" if dias >= 5 else "baixa"
        out.append({"municipio_ibge": cod, "municipio": info.get("nome"), "uf": info.get("uf"), "tipo": tipo,
                    "dias_com_crise": dias, "severidade_max": sev, "probabilidade": prob,
                    "horizonte": "7–30 dias",
                    "acao": f"Preparar resposta a {NOMES_TIPO.get(tipo, tipo)}: pré-cadastrar voluntários e insumos na região."})
    return out
