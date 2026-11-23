"""executar_ingestao e POST /ingest: LLM falso, respostas de feeds gravadas, SQLite temporário (sem rede)."""
import json
import logging

import pytest
from fastapi.testclient import TestClient

from middleware import llm
from middleware.gravacao import TIPOS_CRISE
from middleware.llm import LLMIndisponivel, RespostaLLM
from middleware.tests.falsos import ProvedorFalso, diz

# 3 USGS + 4 GDACS (fixtures, sem as duplicatas) + 9 conflitos fixos do fallback
DISTINTOS = 16


class Classificador:
    """Responde a cada evento com uma classificação válida (severidade 3); `ate` chamadas, depois cai."""

    def __init__(self, ate=None, tipo=None):
        self.chamadas, self.ate, self.tipo = [], ate, tipo

    def completar(self, sistema, historico, ferramentas=()):
        self.chamadas.append((sistema, list(historico), list(ferramentas)))
        if self.ate is not None and len(self.chamadas) > self.ate:
            raise LLMIndisponivel("teto diário de 500 chamadas ao LLM atingido")
        texto = historico[0].texto
        evento = json.loads(texto.split("<evento_nao_confiavel>")[1].split("</evento_nao_confiavel>")[0])
        tipo = self.tipo or evento.get("tipo_sugerido_pela_fonte", "humanitarian")
        return RespostaLLM(texto=json.dumps({"tipo": tipo, "severidade": 3, "urgencia": "48h", "confianca": 0.9,
                                             "justificativa": "teste"}))


@pytest.fixture(autouse=True)
def sem_provedor_global():
    llm.definir_provedor(None)
    llm._padrao = None
    llm._uso.update(dia=None, n=0)
    yield
    llm.definir_provedor(None)
    llm._padrao = None
    llm._uso.update(dia=None, n=0)


def ingerir(app_db, provedor, **kw):
    db = app_db.get_db()
    try:
        from middleware.ingestao_crise import executar_ingestao
        return executar_ingestao(db, llm=provedor, **kw)
    finally:
        db.close()


def test_caminho_feliz_classifica_e_grava_em_python(app_db, rede_gravada):
    p = Classificador()
    r = ingerir(app_db, p)
    assert r["ok"] and r["triggered_by"] == "llm" and r["degradado"] is False and r["errors"] == []
    assert r["cycle_id"] and r["crises_collected"] == DISTINTOS and r["crises_classified"] == DISTINTOS
    assert len(p.chamadas) == DISTINTOS  # duplicatas da coleta não são classificadas de novo
    assert all(c[2] == [] for c in p.chamadas)  # o LLM nunca recebe ferramenta
    linhas = app_db.linhas()
    assert len(linhas) == DISTINTOS
    assert all(l["severity"] == 3 and l["urgency"] == "48h" and l["crisis_type"] in TIPOS_CRISE for l in linhas.values())
    assert len(app_db.avisos) > 0


def test_segunda_rodada_nao_reclassifica_nem_sobrescreve(app_db, rede_gravada):
    ingerir(app_db, Classificador())
    p2 = Classificador()
    r = ingerir(app_db, p2)
    assert p2.chamadas == [] and r["skipped_existing"] == DISTINTOS and r["crises_saved"] == 0


def test_llm_indisponivel_desde_o_inicio_cai_no_fallback(app_db, rede_gravada):
    r = ingerir(app_db, ProvedorFalso([LLMIndisponivel("sem chave")]))
    assert r["ok"] and r["degradado"] is True and "sem chave" in r["motivo"] and r["triggered_by"] == "fallback"
    assert r["crises_classified"] == 0 and r["crises_saved"] == DISTINTOS
    linhas = app_db.linhas()
    assert len(linhas) == DISTINTOS and linhas["gdacs-EQ1578798"]["severity"] == 4  # regra por fonte


def test_teto_no_meio_grava_o_classificado_e_o_resto_por_regra(app_db, rede_gravada):
    r = ingerir(app_db, Classificador(ate=5))
    assert r["degradado"] is True and r["triggered_by"] == "llm+fallback" and r["crises_classified"] == 5
    linhas = app_db.linhas()
    assert len(linhas) == DISTINTOS and r["crises_saved"] == DISTINTOS
    assert sum(1 for l in linhas.values() if l["urgency"] == "48h") == 5  # os 5 do LLM; resto veio das regras


def test_tipo_invalido_do_llm_e_rejeitado_logado_e_nunca_gravado(app_db, rede_gravada, caplog):
    with caplog.at_level(logging.WARNING):
        r = ingerir(app_db, Classificador(tipo="banana"))
    assert r["crises_classified"] == 0 and r["needs_review"] == DISTINTOS
    assert "tipo rejeitado do LLM" in caplog.text and "banana" in caplog.text
    linhas = app_db.linhas()
    assert len(linhas) == DISTINTOS and all(l["crisis_type"] in TIPOS_CRISE for l in linhas.values())
    assert linhas["gdacs-EQ1578798"]["crisis_type"] == "seismic" and linhas["gdacs-EQ1578798"]["severity"] == 4  # valores da fonte


def test_classificacao_existente_nao_e_sobrescrita(app_db, rede_gravada):
    from middleware.gravacao import gravar_eventos
    db = app_db.get_db()
    gravar_eventos(db, [{"id": "gdacs-EQ1578798", "severity": 5, "urgency": "immediate", "crisis_type": "humanitarian"}])
    db.close()
    p = Classificador()
    ingerir(app_db, p)
    assert len(p.chamadas) == DISTINTOS - 1
    assert app_db.linhas()["gdacs-EQ1578798"]["severity"] == 5


# ---------- limite de classificação por ciclo (CRISIS_LLM_MAX_POR_CICLO) ----------

def _ok():
    return diz(json.dumps({"tipo": "seismic", "severidade": 4, "urgencia": "24h", "confianca": 0.9,
                           "justificativa": "teste"}))


def _evento(i, data="sem"):
    e = {"id": f"t-{i}", "title": f"Evento {i}", "country": "X", "country_iso3": "XXX", "lat": 1.0, "lon": 2.0,
         "severity": 1, "urgency": "monitoring", "crisis_type": "seismic", "source": "teste", "people_affected": 0}
    if data != "sem":
        e["date"] = data
    return e


def _marcados(app_db):
    import sqlite3
    conn = sqlite3.connect(app_db.get_db().execute("PRAGMA database_list").fetchone()[2])
    try:
        return {r[0] for r in conn.execute("SELECT crisis_id FROM classifications_log WHERE needs_review=1")}
    finally:
        conn.close()


def test_limite_por_ciclo_classifica_os_mais_recentes_e_o_excedente_vai_ao_fallback(app_db, monkeypatch):
    monkeypatch.setenv("CRISIS_LLM_MAX_POR_CICLO", "2")
    eventos = [_evento(1, "2026-11-20T10:00:00Z"), _evento(2, "2026-11-23T10:00:00Z"), _evento(3),
               _evento(4, "2026-11-22T10:00:00Z"), _evento(5, "2026-11-21T10:00:00Z")]
    p = ProvedorFalso([_ok(), _ok()])
    r = ingerir(app_db, p, coletar=lambda: eventos)
    assert len(p.chamadas) == 2
    assert r["crises_classified"] == 2 and r["excedente_por_limite"] == 3 and r["degradado"] is False
    assert r["crises_saved"] == 5 and r["errors"] == []  # nenhum some
    linhas = app_db.linhas()
    assert set(linhas) == {f"t-{i}" for i in range(1, 6)}
    assert {i for i in linhas if linhas[i]["severity"] == 4} == {"t-2", "t-4"}  # os 2 mais recentes foram ao LLM
    assert {i for i in linhas if linhas[i]["severity"] == 1} == {"t-1", "t-3", "t-5"}  # regra da fonte
    assert _marcados(app_db) == {"t-1", "t-3", "t-5"}  # só o excedente fica marcado para revisão


def test_evento_sem_data_vai_por_ultimo_em_ordem_estavel(app_db, monkeypatch):
    monkeypatch.setenv("CRISIS_LLM_MAX_POR_CICLO", "2")
    eventos = [_evento(1), _evento(2), _evento(3, "2026-11-01T00:00:00Z")]
    p = ProvedorFalso([_ok(), _ok()])
    ingerir(app_db, p, coletar=lambda: eventos)
    vistos = [json.loads(c[1][0].texto.split("<evento_nao_confiavel>")[1].split("</evento_nao_confiavel>")[0])["id"]
              for c in p.chamadas]
    assert vistos == ["t-3", "t-1"]


def test_ids_existentes_nao_sao_reclassificados_em_ciclos_seguintes(app_db, monkeypatch):
    monkeypatch.setenv("CRISIS_LLM_MAX_POR_CICLO", "2")
    eventos = [_evento(i, f"2026-11-0{i}T00:00:00Z") for i in range(1, 6)]
    p1 = ProvedorFalso([_ok(), _ok()])
    ingerir(app_db, p1, coletar=lambda: eventos)
    antes = app_db.linhas()
    p2 = ProvedorFalso([])  # qualquer chamada estoura (roteiro esgotado)
    r = ingerir(app_db, p2, coletar=lambda: eventos)
    assert p2.chamadas == [] and len(p1.chamadas) == 2
    assert r["crises_classified"] == 0 and r["excedente_por_limite"] == 0 and r["crises_saved"] == 0
    assert r["skipped_existing"] == 5
    assert app_db.linhas() == antes  # nada novo gravado nem atualizado (inclusive o excedente do ciclo 1)


def test_limite_e_excedente_coexistem_com_degradado(app_db, monkeypatch):
    monkeypatch.setenv("CRISIS_LLM_MAX_POR_CICLO", "3")
    eventos = [_evento(i, f"2026-11-0{i}T00:00:00Z") for i in range(1, 6)]
    r = ingerir(app_db, ProvedorFalso([_ok(), LLMIndisponivel("teto")]), coletar=lambda: eventos)
    assert r["degradado"] is True and r["crises_classified"] == 1 and r["excedente_por_limite"] == 2
    assert len(app_db.linhas()) == 5 and r["crises_saved"] == 5
    assert _marcados(app_db) == {"t-2", "t-1"}  # só o excedente por limite; o degradado não é marcado


@pytest.mark.parametrize("valor", [None, "abc", "0", "-3"])
def test_limite_invalido_usa_o_padrao_30_e_loga(app_db, monkeypatch, caplog, valor):
    from middleware.ingestao_crise import limite_por_ciclo
    if valor is None:
        monkeypatch.delenv("CRISIS_LLM_MAX_POR_CICLO", raising=False)
    else:
        monkeypatch.setenv("CRISIS_LLM_MAX_POR_CICLO", valor)
    with caplog.at_level(logging.WARNING):
        assert limite_por_ciclo() == 30
    assert ("CRISIS_LLM_MAX_POR_CICLO" in caplog.text) == (valor is not None)


def test_limite_valido_e_lido(monkeypatch):
    from middleware.ingestao_crise import limite_por_ciclo
    monkeypatch.setenv("CRISIS_LLM_MAX_POR_CICLO", "7")
    assert limite_por_ciclo() == 7


# ---------- endpoint ----------

@pytest.fixture
def cli(app_db):
    return TestClient(app_db.app)


def test_endpoint_feliz(app_db, cli, rede_gravada):
    llm.definir_provedor(Classificador())
    corpo = cli.post("/ingest").json()
    assert corpo["ok"] and corpo["degradado"] is False and corpo["crises_collected"] == DISTINTOS
    assert set(corpo) >= {"cycle_id", "crises_collected", "crises_classified", "errors"}
    assert len(app_db.linhas()) == DISTINTOS


def test_endpoint_llm_indisponivel_usa_fallback(app_db, cli, rede_gravada, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # sem provedor injetado e sem chave
    corpo = cli.post("/ingest").json()
    assert corpo["ok"] and corpo["degradado"] is True and "ANTHROPIC_API_KEY" in corpo["motivo"]
    assert len(app_db.linhas()) == DISTINTOS


def test_endpoint_teto_diario_cai_no_fallback(app_db, cli, rede_gravada, monkeypatch):
    monkeypatch.setenv("CRISIS_LLM_LIMITE_DIARIO", "3")
    llm.definir_provedor(Classificador())
    corpo = cli.post("/ingest").json()
    assert corpo["degradado"] is True and "teto diário" in corpo["motivo"] and corpo["crises_classified"] == 3
    assert len(app_db.linhas()) == DISTINTOS


def test_endpoint_duplicado_e_idempotente(app_db, cli, rede_gravada):
    llm.definir_provedor(Classificador())
    cli.post("/ingest")
    corpo = cli.post("/ingest").json()
    assert corpo["crises_saved"] == 0 and corpo["skipped_existing"] == DISTINTOS
    assert len(app_db.linhas()) == DISTINTOS


def test_endpoint_tipo_invalido_rejeitado_e_logado(app_db, cli, rede_gravada, caplog):
    llm.definir_provedor(Classificador(tipo="banana"))
    with caplog.at_level(logging.WARNING):
        corpo = cli.post("/ingest").json()
    assert corpo["needs_review"] == DISTINTOS and "banana" in caplog.text
    assert all(l["crisis_type"] != "banana" for l in app_db.linhas().values())


def test_endpoint_nao_chama_orchestrate(app_db, cli, rede_gravada, monkeypatch):
    monkeypatch.setenv("MONITORING_AGENT_ID", "agente")
    monkeypatch.setattr(app_db, "call_orchestrate", lambda *a, **k: pytest.fail("watsonx não deve ser chamado"))
    llm.definir_provedor(Classificador())
    assert cli.post("/ingest").json()["ok"]
