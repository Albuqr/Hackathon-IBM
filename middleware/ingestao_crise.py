"""Ciclo de ingestão do /ingest sem watsonx: coleta -> classificação (LLM) -> gravação (Python).

- A coleta é a mesma do _ingest_fallback (USGS, EONET, GDACS RSS, GDELT, conflitos fixos).
- O LLM só classifica (classificacao.classificar_evento); quem grava é gravacao.gravar_eventos.
- Eventos repetidos na coleta (mesmo id) são classificados e gravados uma vez; eventos cujo id já existe
  no banco não são reclassificados nem sobrescritos (INSERT-only), o que também poupa o teto diário de LLM.
- LLMIndisponivel (inclui o teto diário) não derruba o ciclo: o que já foi classificado é gravado e o
  restante vai para a rede de segurança por regras (_ingest_fallback); o retorno traz degradado=True.
"""
import logging
from datetime import datetime, timezone

from middleware.classificacao import classificar_evento
from middleware.gravacao import gravar_eventos
from middleware.llm import LLMIndisponivel

log = logging.getLogger(__name__)


def _padroes():
    # Import tardio: middleware.main importa este módulo.
    from middleware import main
    return main._coletar_eventos, main._ingest_fallback, main._avisar_novos


def _aplicar(evento: dict, cls: dict) -> dict:
    return {**evento, "severity": cls["severidade"], "urgency": cls["urgencia"], "crisis_type": cls["tipo"]}


def executar_ingestao(db, llm=None, *, coletar=None, fallback=None, ao_gravar=None) -> dict:
    """Roda um ciclo. `db`: conexão sqlite3. `llm`: objeto com .completar (padrão middleware.llm).

    coletar() -> lista de eventos; fallback(eventos) -> dict (rede de segurança); ao_gravar(eventos) avisa
    os novos (Telegram). Os três têm como padrão as funções de middleware.main (injetáveis em teste).
    """
    padrao = _padroes() if None in (coletar, fallback, ao_gravar) else None
    coletar = coletar or padrao[0]
    fallback = fallback or padrao[1]
    ao_gravar = ao_gravar or padrao[2]

    ciclo = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    coletados, vistos = [], set()
    for e in coletar():
        if e.get("id") and e["id"] not in vistos:  # dedup por id na coleta
            vistos.add(e["id"])
            coletados.append(e)
    existentes = {r[0] for r in db.execute("SELECT id FROM crises")}
    novos = [e for e in coletados if e["id"] not in existentes]

    gravar, errors = [], []
    classificados = revisar = 0
    pendentes, motivo = [], None
    for i, ev in enumerate(novos):
        try:
            cls = classificar_evento(ev, llm=llm)
        except LLMIndisponivel as e:
            motivo, pendentes = str(e), novos[i:]
            log.warning("LLM indisponível na ingestão (%s); %d evento(s) vão para o fallback", motivo, len(pendentes))
            break
        gravar.append(_aplicar(ev, cls))
        if cls["needs_review"]:
            revisar += 1
        else:
            classificados += 1

    res = gravar_eventos(db, gravar, atualizar=False) if gravar else {"saved": 0, "ids": [], "errors": []}
    errors += res["errors"]
    if res["ids"]:
        gravados = set(res["ids"])
        ao_gravar([e for e in gravar if e["id"] in gravados])

    saida = {
        "ok": True, "triggered_by": "llm", "cycle_id": ciclo,
        "crises_collected": len(coletados), "crises_classified": classificados,
        "crises_saved": res["saved"], "events_saved": res["saved"], "needs_review": revisar,
        "skipped_existing": len(coletados) - len(novos), "errors": errors, "degradado": False,
    }
    if motivo is not None:
        fb = fallback(pendentes)
        saida.update(
            triggered_by="fallback" if not gravar else "llm+fallback", degradado=True, motivo=motivo,
            crises_saved=res["saved"] + fb.get("events_saved", 0), events_saved=res["saved"] + fb.get("events_saved", 0),
            errors=errors + list(fb.get("errors", [])),
        )
    return saida
