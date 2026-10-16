"""Ingestão do Dash Brasil (FR-015, FR-017–FR-023).

Coleta as fontes brasileiras (tools/br_*.py) e as 5 fontes globais atuais (importadas
sem alteração), mantém só eventos dentro do Brasil, atribui o município IBGE e grava
no brasil.db. Uma fonte com falha não interrompe as outras (FR-023).
"""
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from . import db, malha
from .config import Config

_TOOLS = os.path.join(os.path.dirname(__file__), "..", "..", "tools")

FONTES_BR = ("inpe", "cemaden", "inmet", "noticias")
FONTES_GLOBAIS = ("usgs", "gdacs", "eonet", "reliefweb", "gdelt")

QUEIMADA_SEM_FOCO = timedelta(hours=48)


def _tools():
    if _TOOLS not in sys.path:
        sys.path.insert(0, _TOOLS)


def fontes_padrao() -> dict:
    """Nome da fonte → função sem argumentos que devolve a lista de eventos da ferramenta."""
    _tools()

    def chamar(modulo, funcao, **kw):
        def f():
            return executar_ferramenta(getattr(__import__(modulo), funcao), **kw)
        return f

    return {
        "inpe": chamar("br_inpe_queimadas", "br_inpe_queimadas"),
        "cemaden": chamar("br_cemaden", "br_cemaden"),
        "inmet": chamar("br_inmet", "br_inmet"),
        "usgs": chamar("fetch_usgs", "fetch_usgs", days=7),
        "gdacs": chamar("fetch_gdacs", "fetch_gdacs", alert_level="green;orange;red"),
        "eonet": chamar("fetch_eonet", "fetch_eonet", days=30, status="open"),
        "reliefweb": chamar("fetch_reliefweb", "fetch_reliefweb"),
        "gdelt": chamar("fetch_conflict_data", "fetch_conflict_data", include_fallback=False),
    }


def executar_ferramenta(ferramenta, **kw):
    """Chama uma ferramenta decorada com @tool do watsonx e devolve o resultado puro.

    No ibm-watsonx-orchestrate 2.8.0, chamar o objeto PythonTool devolve um ToolResponse
    (resultado em `.content`); a função original fica em `.fn`.
    """
    resultado = getattr(ferramenta, "fn", ferramenta)(**kw)
    return getattr(resultado, "content", resultado)


def utc(valor, padrao: datetime) -> datetime:
    """Converte os vários formatos de data das fontes para datetime UTC; sem fuso = UTC."""
    if not valor:
        return padrao
    s = str(valor).strip().replace(" ", "T").replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return padrao
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat(timespec="seconds")


def _municipio(ev: dict, m: malha.Malha):
    cod = ev.get("municipio_ibge")
    if cod and m.info(int(cod)):
        return int(cod)
    try:
        return m.municipio_em(float(ev["lat"]), float(ev["lon"]))
    except (KeyError, TypeError, ValueError):
        return None


def _gravar(conn, ev: dict, cod, uf, agora: datetime):
    visto = utc(ev.get("visto_em"), agora)
    if ev["source"] == "inpe":
        expira = visto + QUEIMADA_SEM_FOCO
    elif ev.get("expira_em"):
        expira = utc(ev["expira_em"], agora + timedelta(days=1))
    else:
        expira = None  # sai quando some da fonte (ver _expirar_ausentes)
    noticia = ev.get("verificacao") == "nao_verificada"
    sev = float(ev.get("severity") or 1)
    if noticia:
        sev = min(sev, 3)  # FR-024: crise de notícia não verificada tem teto 3
    # Decisão do admin sobre notícia (FR-025) é preservada: confirmada não expira nem perde a severidade
    # que o admin deu; descartada continua descartada.
    conn.execute(
        """INSERT INTO crises (id, title, country, country_iso3, lat, lon, severity, urgency, crisis_type,
               source, people_affected, created_at, updated_at, municipio_ibge, uf, link_fonte,
               municipios_afetados, visto_em, expira_em, verificacao)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET title=excluded.title, lat=excluded.lat, lon=excluded.lon,
               severity=CASE WHEN crises.source='noticias' AND crises.verificacao!='nao_verificada'
                             THEN crises.severity ELSE excluded.severity END,
               urgency=excluded.urgency, crisis_type=excluded.crisis_type,
               people_affected=excluded.people_affected, updated_at=excluded.updated_at,
               municipio_ibge=excluded.municipio_ibge, uf=excluded.uf, link_fonte=excluded.link_fonte,
               municipios_afetados=excluded.municipios_afetados, visto_em=excluded.visto_em,
               expira_em=CASE WHEN crises.source='noticias' AND crises.verificacao='verificada'
                              THEN NULL ELSE excluded.expira_em END""",
        (ev["id"], ev.get("title", ""), "Brasil", "BRA", float(ev["lat"]), float(ev["lon"]),
         sev, ev.get("urgency") or "monitoring", ev.get("crisis_type") or "humanitarian",
         ev["source"], int(ev.get("people_affected") or 0), iso(agora), iso(agora), cod, uf,
         ev.get("link_fonte"), json.dumps(ev.get("municipios_afetados") or ([cod] if cod else [])),
         iso(visto), iso(expira) if expira else None, "nao_verificada" if noticia else "verificada"),
    )
    # histórico diário por crise (FR-034: previsões por recorrência)
    dia = iso(agora)[:10]
    if not conn.execute("SELECT 1 FROM classifications_log WHERE crisis_id=? AND substr(classified_at,1,10)=?",
                        (ev["id"], dia)).fetchone():
        conn.execute("INSERT INTO classifications_log (crisis_id, severity, crisis_type, classified_at) VALUES (?,?,?,?)",
                     (ev["id"], sev, ev.get("crisis_type"), iso(agora)))


def _expirar_ausentes(conn, fonte: str, ids: set, agora: datetime):
    """Fontes sem data de fim (CEMADEN, globais): crise que não veio na última coleta OK sai do mapa."""
    linhas = conn.execute(
        "SELECT id FROM crises WHERE source=? AND (expira_em IS NULL OR expira_em > ?)", (fonte, iso(agora))
    ).fetchall()
    for (cid,) in linhas:
        if cid not in ids:
            conn.execute("UPDATE crises SET expira_em=? WHERE id=?", (iso(agora), cid))


def executar(cfg: Config, fontes: dict | None = None, agora: datetime | None = None) -> dict:
    agora = agora or datetime.now(timezone.utc)
    fontes = fontes or fontes_padrao()
    m = malha.carregar()
    inicio = time.monotonic()
    relatorio = {"fontes": {}, "gravadas": 0, "sem_municipio": 0}
    conn = db.conectar(cfg)
    try:
        for nome, buscar in fontes.items():
            try:
                eventos = buscar()
                erros = [e for e in eventos if e.get("error")]
                if erros and len(erros) == len(eventos):
                    raise RuntimeError(erros[0]["error"])
            except Exception as e:  # FR-023: uma fonte falha, as outras seguem
                conn.execute(
                    """INSERT INTO fontes_status (fonte, ok, eventos, erro, tentativa_em) VALUES (?,0,0,?,?)
                       ON CONFLICT(fonte) DO UPDATE SET ok=0, eventos=0, erro=excluded.erro,
                       tentativa_em=excluded.tentativa_em""",
                    (nome, str(e)[:300], iso(agora)),
                )
                conn.commit()
                relatorio["fontes"][nome] = {"ok": False, "erro": str(e)[:300]}
                continue

            ids = set()
            for ev in eventos:
                if ev.get("error") or ev.get("lat") is None or ev.get("lon") is None:
                    continue
                ev.setdefault("source", nome)
                cod = _municipio(ev, m)
                if cod is None:
                    if nome in FONTES_GLOBAIS:
                        continue  # FR-020: fora do Brasil
                    relatorio["sem_municipio"] += 1
                info = m.info(cod) if cod else None
                ev["id"] = ev["id"] if nome in FONTES_BR else f"br-{ev['id']}"
                _gravar(conn, ev, cod, info["uf"] if info else None, agora)
                ids.add(ev["id"])
            if nome not in ("inpe", "inmet", "noticias"):  # essas expiram por data
                _expirar_ausentes(conn, ev_fonte(nome, eventos), ids, agora)
            conn.execute(
                """INSERT INTO fontes_status (fonte, ok, eventos, erro, tentativa_em, ultimo_ok_em) VALUES (?,1,?,NULL,?,?)
                   ON CONFLICT(fonte) DO UPDATE SET ok=1, eventos=excluded.eventos, erro=NULL,
                   tentativa_em=excluded.tentativa_em, ultimo_ok_em=excluded.ultimo_ok_em""",
                (nome, len(ids), iso(agora), iso(agora)),
            )
            conn.commit()
            relatorio["fontes"][nome] = {"ok": True, "eventos": len(ids)}
            relatorio["gravadas"] += len(ids)
    finally:
        conn.close()
    relatorio["segundos"] = round(time.monotonic() - inicio, 1)
    return relatorio


def ev_fonte(nome: str, eventos: list) -> str:
    """Valor da coluna `source` que a fonte grava (as ferramentas globais já trazem o seu)."""
    return next((e["source"] for e in eventos if e.get("source") and not e.get("error")), nome)


def status(cfg: Config) -> list[dict]:
    conn = db.conectar(cfg)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM fontes_status ORDER BY fonte")]
    finally:
        conn.close()


def crises_ativas(cfg: Config, agora: datetime | None = None) -> list[dict]:
    agora = agora or datetime.now(timezone.utc)
    conn = db.conectar(cfg)
    try:
        linhas = conn.execute(
            """SELECT c.*, (SELECT COUNT(*) FROM crisis_associations a WHERE a.crisis_id=c.id) AS inscritos
               FROM crises c
               WHERE (c.expira_em IS NULL OR c.expira_em > ?) AND c.verificacao != 'descartada'
               ORDER BY c.severity DESC""",
            (iso(agora),),
        ).fetchall()
        out = []
        for r in linhas:
            d = dict(r)
            d["municipios_afetados"] = json.loads(d.get("municipios_afetados") or "[]")
            out.append(d)
        return out
    finally:
        conn.close()


def laco_automatico(cfg: Config, parar: threading.Event, executar_fn=None, esperar=None):
    """FR-016: a cada BRASIL_INGESTAO_AUTO_MIN minutos (a primeira depois do primeiro intervalo)."""
    executar_fn = executar_fn or executar
    esperar = esperar or parar.wait
    while not esperar(cfg.ingestao_auto_min * 60):
        try:
            rel = executar_fn(cfg)
            print(f"[brasil] ingestão automática: {rel.get('gravadas')} crises em {rel.get('segundos')}s")
        except Exception as e:  # o laço não morre por uma ingestão com erro
            print(f"[brasil] ingestão automática falhou: {e}")


def iniciar_automatico(cfg: Config) -> threading.Event | None:
    if cfg.ingestao_auto_min <= 0:
        return None
    parar = threading.Event()
    threading.Thread(target=laco_automatico, args=(cfg, parar), daemon=True, name="brasil-ingestao").start()
    return parar
