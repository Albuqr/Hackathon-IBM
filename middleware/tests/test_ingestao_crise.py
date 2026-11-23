"""executar_ingestao e POST /ingest: LLM falso, respostas de feeds gravadas, SQLite temporário (sem rede)."""
import json
import logging

import pytest
from fastapi.testclient import TestClient

from middleware import llm
from middleware.gravacao import TIPOS_CRISE
from middleware.llm import LLMIndisponivel, RespostaLLM
from middleware.tests.falsos import ProvedorFalso

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


def ingerir(app_db, provedor):
    db = app_db.get_db()
    try:
        from middleware.ingestao_crise import executar_ingestao
        return executar_ingestao(db, llm=provedor)
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
