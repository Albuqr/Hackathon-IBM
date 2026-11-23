"""middleware/llm.py: conversão neutro<->Anthropic, erros e disponibilidade (sem rede)."""
import builtins
import sys
from types import SimpleNamespace as NS

import pytest

from middleware import llm
from middleware.llm import (ChamadaFerramenta, EspecFerramenta, LLMIndisponivel, Mensagem, ProvedorAnthropic,
                            RespostaLLM, ResultadoFerramenta, TurnoResultados)
from middleware.tests.falsos import ProvedorFalso, diz


@pytest.fixture(autouse=True)
def limpo(monkeypatch):
    llm.definir_provedor(None)
    llm._padrao = None
    llm._uso.update(dia=None, n=0)
    for v in ("CRISIS_LLM_MODELO", "CRISIS_LLM_MAX_TOKENS", "CRISIS_LLM_TIMEOUT", "CRISIS_LLM_LIMITE_DIARIO"):
        monkeypatch.delenv(v, raising=False)
    yield
    llm.definir_provedor(None)
    llm._padrao = None


def test_historico_neutro_vira_formato_anthropic():
    hist = [Mensagem("user", "oi"),
            RespostaLLM("vou ver", [ChamadaFerramenta("t1", "fetch_usgs", {"days": 1})]),
            TurnoResultados([ResultadoFerramenta("t1", "[]"), ResultadoFerramenta("t2", "boom", erro=True)])]
    assert llm.para_anthropic_mensagens(hist) == [
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": [{"type": "text", "text": "vou ver"},
                                          {"type": "tool_use", "id": "t1", "name": "fetch_usgs", "input": {"days": 1}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "[]"},
                                     {"type": "tool_result", "tool_use_id": "t2", "content": "boom", "is_error": True}]},
    ]


def test_item_de_historico_desconhecido():
    with pytest.raises(TypeError):
        llm.para_anthropic_mensagens(["solto"])


def test_ferramentas_viram_formato_anthropic():
    f = EspecFerramenta("x", "desc", {"type": "object", "properties": {"a": {"type": "string"}}})
    assert llm.para_anthropic_ferramentas([f]) == [{"name": "x", "description": "desc", "input_schema": f.schema_json}]


def test_resposta_anthropic_vira_neutra():
    resp = NS(content=[NS(type="text", text="a"), NS(type="tool_use", id="t9", name="n", input={"k": 1}),
                       NS(type="thinking")])
    r = llm.de_anthropic_resposta(resp)
    assert r == RespostaLLM("a", [ChamadaFerramenta("t9", "n", {"k": 1})])


class ClienteFalso:
    def __init__(self, resp=None, erro=None):
        self.resp, self.erro, self.args = resp, erro, None
        self.messages = NS(create=self._create)

    def _create(self, **kw):
        self.args = kw
        if self.erro:
            raise self.erro
        return self.resp


def test_provedor_anthropic_monta_chamada_com_config_do_env(monkeypatch):
    monkeypatch.setenv("CRISIS_LLM_MODELO", "modelo-x")
    monkeypatch.setenv("CRISIS_LLM_MAX_TOKENS", "77")
    c = ClienteFalso(NS(content=[NS(type="text", text="ok")]))
    r = ProvedorAnthropic(c).completar("sis", [Mensagem("user", "oi")], [EspecFerramenta("x", "d")])
    assert r.texto == "ok"
    assert c.args["model"] == "modelo-x" and c.args["max_tokens"] == 77 and c.args["system"] == "sis"
    assert c.args["tools"][0]["name"] == "x"


def test_padroes_e_env_invalido(monkeypatch):
    assert llm.modelo() == "claude-haiku-5-5"
    monkeypatch.setenv("CRISIS_LLM_MAX_TOKENS", "abc")
    c = ClienteFalso(NS(content=[]))
    ProvedorAnthropic(c).completar("", [Mensagem("user", "oi")])
    assert c.args["max_tokens"] == llm.MAX_TOKENS_PADRAO and "system" not in c.args and "tools" not in c.args


def test_erro_do_provedor_vira_llm_indisponivel():
    class ErroDoSDK(Exception):
        pass
    with pytest.raises(LLMIndisponivel) as e:
        ProvedorAnthropic(ClienteFalso(erro=ErroDoSDK("segredo"))).completar("", [Mensagem("user", "oi")])
    assert "ErroDoSDK" in str(e.value) and "segredo" not in str(e.value)


def test_completar_embrulha_excecao_de_provedor_injetado():
    with pytest.raises(LLMIndisponivel):
        llm.completar("", [], provedor=ProvedorFalso([RuntimeError("x")]))


def test_definir_provedor_e_disponivel():
    llm.definir_provedor(ProvedorFalso([diz("oi")]))
    assert llm.disponivel() is True
    assert llm.completar("", [Mensagem("user", "a")]).texto == "oi"


def _sem_anthropic(monkeypatch):
    monkeypatch.delitem(sys.modules, "anthropic", raising=False)
    real = builtins.__import__

    def falso(nome, *a, **k):
        if nome == "anthropic":
            raise ImportError("sem anthropic")
        return real(nome, *a, **k)
    monkeypatch.setattr(builtins, "__import__", falso)


def test_anthropic_ausente(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    _sem_anthropic(monkeypatch)
    assert llm.disponivel() is False
    with pytest.raises(LLMIndisponivel, match="não instalado"):
        llm.completar("", [Mensagem("user", "oi")])


def test_sem_chave(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm.disponivel() is False
    with pytest.raises(LLMIndisponivel, match="ANTHROPIC_API_KEY"):
        llm.completar("", [Mensagem("user", "oi")])


# ---------- teto diário ----------

def test_teto_diario_bloqueia_sem_chamar_o_provedor(monkeypatch):
    monkeypatch.setenv("CRISIS_LLM_LIMITE_DIARIO", "2")
    p = ProvedorFalso([diz("a"), diz("b"), diz("c")])
    llm.completar("", [], provedor=p)
    llm.completar("", [], provedor=p)
    with pytest.raises(LLMIndisponivel, match="teto diário de 2"):
        llm.completar("", [], provedor=p)
    assert len(p.chamadas) == 2 and llm.chamadas_hoje() == 2


def test_teto_diario_zera_no_dia_seguinte(monkeypatch):
    monkeypatch.setenv("CRISIS_LLM_LIMITE_DIARIO", "1")
    dia = ["2026-01-01"]
    monkeypatch.setattr(llm, "_hoje", lambda: dia[0])
    p = ProvedorFalso([diz("a"), diz("b")])
    llm.completar("", [], provedor=p)
    with pytest.raises(LLMIndisponivel):
        llm.completar("", [], provedor=p)
    dia[0] = "2026-01-02"
    assert llm.chamadas_hoje() == 0
    assert llm.completar("", [], provedor=p).texto == "b"


def test_teto_diario_conta_tentativas_que_falham(monkeypatch):
    monkeypatch.setenv("CRISIS_LLM_LIMITE_DIARIO", "1")
    p = ProvedorFalso([RuntimeError("x"), diz("nunca")])
    with pytest.raises(LLMIndisponivel, match="falha do provedor"):
        llm.completar("", [], provedor=p)
    with pytest.raises(LLMIndisponivel, match="teto diário"):
        llm.completar("", [], provedor=p)
    assert len(p.chamadas) == 1


def test_teto_diario_padrao_500_e_env_invalido(monkeypatch):
    assert llm.limite_diario() == 500
    monkeypatch.setenv("CRISIS_LLM_LIMITE_DIARIO", "abc")
    assert llm.limite_diario() == 500


def test_teto_diario_thread_safe(monkeypatch):
    import threading
    monkeypatch.setenv("CRISIS_LLM_LIMITE_DIARIO", "20")
    class P:
        def completar(self, *a):
            return diz("ok")
    ok, bloq = [], []

    def tarefa():
        try:
            llm.completar("", [], provedor=P()); ok.append(1)
        except LLMIndisponivel:
            bloq.append(1)
    ts = [threading.Thread(target=tarefa) for _ in range(60)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(ok) == 20 and len(bloq) == 40
