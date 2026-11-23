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
    for v in ("CRISIS_LLM_MODELO", "CRISIS_LLM_MAX_TOKENS", "CRISIS_LLM_TIMEOUT"):
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
