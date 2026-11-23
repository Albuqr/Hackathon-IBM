"""middleware/agentes.py: laço de ferramentas com provedor falso, sem rede."""
import sys

import pytest
import yaml

from middleware import agentes
from middleware.agentes import AgenteNaoEncontrado, executar
from middleware.llm import LLMIndisponivel, Mensagem, RespostaLLM, TurnoResultados
from middleware.tests.falsos import ProvedorFalso, diz, pede


def fake_usgs(min_magnitude: float = 4.5, days: int = 1) -> list:
    """Busca terremotos.

    Args:
        min_magnitude: Magnitude minima.
        days: Dias.
    """
    return [{"id": "u1", "magnitude": min_magnitude}]


def test_agente_sem_tool_responde_texto_com_instructions_do_yaml():
    real = yaml.safe_load(open(agentes.RAIZ / "agents" / "assistant_agent.yaml", encoding="utf-8"))["instructions"]
    p = ProvedorFalso([diz("Resumo da necessidade: ...")])
    r = executar("assistant_agent", "Preciso de ajuda", llm=p)
    assert r.texto.startswith("Resumo") and r.passos == [] and r.erro is None
    sistema, hist, ferr = p.chamadas[0]
    assert sistema == real and "Resumo da necessidade" in sistema
    assert ferr == [] and hist == [Mensagem("user", "Preciso de ajuda")]


def test_contexto_e_concatenado_de_forma_explicita():
    p = ProvedorFalso([diz("ok")])
    executar("assistant_agent", "oi", contexto={"cidade": "Recife"}, llm=p)
    assert p.chamadas[0][1][0].texto == 'oi\n\nContexto:\n{"cidade": "Recife"}'


def test_agente_com_tool_executa_e_devolve_resultado():
    p = ProvedorFalso([pede("fetch_usgs", {"min_magnitude": 6.0}), diz("Achei 1 terremoto")])
    r = executar("monitoring_agent", "monitore", llm=p, ferramentas={"fetch_usgs": fake_usgs})
    assert r.texto == "Achei 1 terremoto" and r.erro is None
    assert [(s.ferramenta, s.args, s.erro) for s in r.passos] == [("fetch_usgs", {"min_magnitude": 6.0}, False)]
    # o segundo turno recebeu o resultado em formato neutro
    ultimo = p.chamadas[1][1][-1]
    assert isinstance(ultimo, TurnoResultados)
    assert ultimo.resultados[0].id == "t1" and '"magnitude": 6.0' in ultimo.resultados[0].conteudo
    assert not ultimo.resultados[0].erro


def test_schema_derivado_da_assinatura_e_docstring():
    p = ProvedorFalso([diz("ok")])
    executar("monitoring_agent", "x", llm=p, ferramentas={"fetch_usgs": fake_usgs})
    espec = next(f for f in p.chamadas[0][2] if f.nome == "fetch_usgs")
    assert espec.descricao == "Busca terremotos."
    assert espec.schema_json == {"type": "object", "properties": {
        "min_magnitude": {"type": "number", "description": "Magnitude minima."},
        "days": {"type": "integer", "description": "Dias."}}}


def test_ferramenta_que_levanta_excecao_nao_derruba_o_laco():
    def quebra(days: int = 1):
        raise RuntimeError("API fora")
    p = ProvedorFalso([pede("fetch_usgs"), diz("não consegui")])
    r = executar("monitoring_agent", "x", llm=p, ferramentas={"fetch_usgs": quebra})
    assert r.texto == "não consegui" and r.passos[0].erro is True
    res = p.chamadas[1][1][-1].resultados[0]
    assert res.erro is True and "RuntimeError" in res.conteudo and "API fora" in res.conteudo


def test_nome_fora_da_lista_de_permissao_vira_erro_sem_executar():
    chamou = []
    p = ProvedorFalso([pede("save_classification"), diz("ok")])
    r = executar("monitoring_agent", "x", llm=p,
                 ferramentas={"save_classification": lambda **k: chamou.append(1)})
    assert chamou == [] and r.passos[0].erro is True and "não permitida" in r.passos[0].conteudo


def test_agente_sem_tools_nao_executa_ferramenta_pedida():
    p = ProvedorFalso([pede("fetch_usgs"), diz("ok")])
    r = executar("assistant_agent", "x", llm=p, ferramentas={"fetch_usgs": fake_usgs})
    assert r.passos[0].erro is True and "não permitida" in r.passos[0].conteudo


def test_max_passos_devolve_erro_controlado():
    p = ProvedorFalso([pede("fetch_usgs", id=f"t{i}") for i in range(5)])
    r = executar("monitoring_agent", "x", llm=p, ferramentas={"fetch_usgs": fake_usgs}, max_passos=3)
    assert r.erro and "max_passos" in r.erro and len(r.passos) == 3 and r.texto == ""


def test_yaml_inexistente_e_nome_invalido():
    with pytest.raises(AgenteNaoEncontrado):
        executar("nao_existe", "x", llm=ProvedorFalso([]))
    with pytest.raises(AgenteNaoEncontrado):
        executar("../README", "x", llm=ProvedorFalso([]))


def test_falha_do_provedor_propaga_llm_indisponivel():
    with pytest.raises(LLMIndisponivel):
        executar("assistant_agent", "x", llm=ProvedorFalso([LLMIndisponivel("fora")]))


def test_carrega_tool_real_sem_orchestrate_e_sem_alterar_sys_modules():
    antes = sys.modules.get("ibm_watsonx_orchestrate")
    fn = agentes._carregar_ferramenta("fetch_usgs")
    assert callable(fn) and fn.__name__ == "fetch_usgs"
    assert sys.modules.get("ibm_watsonx_orchestrate") is antes
    spec = agentes.espec_da_funcao("fetch_usgs", fn)
    assert spec.schema_json["properties"]["min_magnitude"]["type"] == "number"


def test_tool_com_dependencia_ausente_fica_de_fora_sem_derrubar():
    # classify_crisis importa ibm_watsonx_ai (pode não estar instalado); o agente roda mesmo assim
    p = ProvedorFalso([diz("ok")])
    r = executar("classification_agent", "x", llm=p, ferramentas={"save_classification": lambda **k: "{}"})
    assert r.texto == "ok"
    nomes = {f.nome for f in p.chamadas[0][2]}
    assert "save_classification" in nomes
