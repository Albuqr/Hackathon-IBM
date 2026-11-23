"""Executa um agente de agents/<agente>.yaml sobre a camada neutra de LLM (middleware/llm.py).

- instructions/nome/descrição vêm do YAML; as ferramentas são só as listadas em `tools:` do YAML
  (lista de permissão): nome desconhecido pedido pelo LLM vira erro de ferramenta, nunca execução.
- As funções vêm de tools/<nome>.py SEM o SDK do orchestrate: o arquivo é executado com um stub
  temporário do decorador `@tool` (devolve a função intacta). Os arquivos de tools/ não mudam, então
  a publicação no watsonx (import_all.py) continua igual.
- Este módulo só trafega o formato neutro de llm.py. Falha do provedor propaga LLMIndisponivel
  (quem chama decide o fallback/resposta degradada).
"""
import importlib.util
import inspect
import json
import logging
import re
import sys
import types
import typing
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from middleware import llm as _llm
from middleware.llm import (ChamadaFerramenta, EspecFerramenta, Mensagem, RespostaLLM, ResultadoFerramenta,
                            TurnoResultados)

log = logging.getLogger("middleware.agentes")

RAIZ = Path(__file__).resolve().parent.parent
MAX_PASSOS_PADRAO = 6
MAX_CONTEUDO = 20000  # teto de caracteres de um resultado de ferramenta devolvido ao LLM


class AgenteNaoEncontrado(Exception):
    pass


@dataclass
class Passo:
    """Uma ferramenta chamada: nome, argumentos, conteúdo devolvido ao LLM e se falhou."""
    ferramenta: str
    args: dict
    conteudo: str
    erro: bool = False


@dataclass
class Resultado:
    texto: str = ""
    passos: list = field(default_factory=list)
    erro: str | None = None


# ---------- YAML ----------

def carregar_agente(agente: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_]+", agente or ""):
        raise AgenteNaoEncontrado(f"nome de agente inválido: {agente!r}")
    caminho = RAIZ / "agents" / f"{agente}.yaml"
    if not caminho.is_file():
        raise AgenteNaoEncontrado(f"agente não encontrado: {agente}")
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    if not dados.get("instructions"):
        raise AgenteNaoEncontrado(f"agente sem instructions: {agente}")
    return dados


# ---------- ferramentas: carga sem o SDK do orchestrate ----------

_cache_ferramentas: dict = {}


def _stub_tool(*args, **kwargs):
    """@tool e @tool(...): devolve a função original sem alterá-la."""
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0]
    return lambda fn: fn


def _carregar_ferramenta(nome: str):
    if nome in _cache_ferramentas:
        return _cache_ferramentas[nome]
    caminho = RAIZ / "tools" / f"{nome}.py"
    if not re.fullmatch(r"[A-Za-z0-9_]+", nome) or not caminho.is_file():
        raise ImportError(f"ferramenta não encontrada: {nome}")
    nomes = ["ibm_watsonx_orchestrate", "ibm_watsonx_orchestrate.agent_builder",
             "ibm_watsonx_orchestrate.agent_builder.tools"]
    antes = {n: sys.modules.get(n) for n in nomes}
    try:
        for n in nomes:
            sys.modules[n] = types.ModuleType(n)
        sys.modules[nomes[-1]].tool = _stub_tool
        spec = importlib.util.spec_from_file_location(f"_tools_agentes.{nome}", caminho)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        for n, m in antes.items():
            if m is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = m
    fn = getattr(mod, nome, None)
    if not callable(fn):
        raise ImportError(f"{nome}.py não define a função {nome}")
    _cache_ferramentas[nome] = fn
    return fn


# ---------- schema derivado de assinatura, type hints e docstring ----------

_TIPOS = {int: "integer", float: "number", str: "string", bool: "boolean", list: "array", dict: "object"}


def _tipo_json(anot) -> dict:
    origem = typing.get_origin(anot) or anot
    if origem in (typing.Union, types.UnionType):
        restantes = [a for a in typing.get_args(anot) if a is not type(None)]
        return _tipo_json(restantes[0]) if len(restantes) == 1 else {}
    tipo = _TIPOS.get(origem)
    return {"type": tipo} if tipo else {}


def _docstring(fn) -> tuple[str, dict]:
    """Descrição (texto antes de 'Args:') e descrição por parâmetro (linhas 'nome: texto' em Args)."""
    doc = inspect.getdoc(fn) or ""
    corpo, _, resto = doc.partition("Args:")
    args = {}
    atual = None
    for linha in resto.split("Returns:")[0].splitlines():
        indent = len(linha) - len(linha.lstrip())
        m = re.match(r"\s*(\w+)\s*:\s*(.*)", linha)
        if m and indent <= 4:
            atual = m.group(1)
            args[atual] = m.group(2).strip()
        elif atual and linha.strip():
            args[atual] += " " + linha.strip()
    return corpo.strip(), args


def espec_da_funcao(nome: str, fn) -> EspecFerramenta:
    descricao, docs = _docstring(fn)
    try:
        dicas = typing.get_type_hints(fn)
    except Exception:
        dicas = {}
    props, obrigatorios = {}, []
    for p in inspect.signature(fn).parameters.values():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        props[p.name] = _tipo_json(dicas.get(p.name, p.annotation))
        if docs.get(p.name):
            props[p.name]["description"] = docs[p.name]
        if p.default is p.empty:
            obrigatorios.append(p.name)
    schema = {"type": "object", "properties": props}
    if obrigatorios:
        schema["required"] = obrigatorios
    return EspecFerramenta(nome=nome, descricao=descricao or nome, schema_json=schema)


# ---------- execução ----------

def _serializar(valor) -> str:
    texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, default=str)
    if len(texto) > MAX_CONTEUDO:
        texto = texto[:MAX_CONTEUDO] + f"... [truncado, {len(texto)} caracteres]"
    return texto


def _executar_chamada(chamada: ChamadaFerramenta, funcoes: dict) -> tuple[ResultadoFerramenta, Passo]:
    fn = funcoes.get(chamada.nome)
    if fn is None:
        conteudo, erro = f"ferramenta não permitida para este agente: {chamada.nome}", True
    else:
        try:
            conteudo, erro = _serializar(fn(**(chamada.args or {}))), False
        except Exception as e:
            log.warning("ferramenta %s falhou: %s", chamada.nome, type(e).__name__)
            conteudo, erro = f"erro ao executar {chamada.nome}: {type(e).__name__}: {e}", True
    return (ResultadoFerramenta(chamada.id, conteudo, erro),
            Passo(chamada.nome, dict(chamada.args or {}), conteudo, erro))


def _contexto_texto(contexto) -> str:
    if contexto is None or contexto == "":
        return ""
    return contexto if isinstance(contexto, str) else json.dumps(contexto, ensure_ascii=False, default=str)


def executar(agente: str, mensagem: str, *, contexto=None, llm=None, ferramentas: dict | None = None,
             max_passos: int = MAX_PASSOS_PADRAO) -> Resultado:
    """Roda `agente` com `mensagem` (+ `contexto` opcional, anexado ao fim da mensagem sob 'Contexto:').

    llm: objeto com .completar(sistema, historico, ferramentas) (padrão: o módulo middleware.llm).
    ferramentas: {nome: função} para substituir as de tools/ (testes); só vale para nomes do YAML.
    max_passos: máximo de chamadas ao LLM; estourar devolve Resultado com erro, sem levantar.
    Levanta AgenteNaoEncontrado (YAML ausente) e LLMIndisponivel (falha do provedor).
    """
    cfg = carregar_agente(agente)
    permitidas = [t for t in (cfg.get("tools") or []) if isinstance(t, str)]
    funcoes = {}
    for nome in permitidas:
        try:
            funcoes[nome] = (ferramentas or {}).get(nome) or _carregar_ferramenta(nome)
        except Exception as e:  # ex.: dependência da tool ausente (ibm_watsonx_ai); o agente roda sem ela
            log.warning("ferramenta %s indisponível para %s: %s", nome, agente, type(e).__name__)
    especs = [espec_da_funcao(n, f) for n, f in funcoes.items()]

    texto_usuario = mensagem
    ctx = _contexto_texto(contexto)
    if ctx:
        texto_usuario = f"{mensagem}\n\nContexto:\n{ctx}"
    historico = [Mensagem("user", texto_usuario)]
    completar = (llm or _llm).completar
    res = Resultado()

    for _ in range(max_passos):
        resp: RespostaLLM = completar(cfg["instructions"], historico, especs)
        if not resp.chamadas:
            res.texto = resp.texto
            return res
        historico.append(resp)
        resultados = []
        for chamada in resp.chamadas:
            r, passo = _executar_chamada(chamada, funcoes)
            resultados.append(r)
            res.passos.append(passo)
        historico.append(TurnoResultados(resultados))
    res.erro = f"max_passos ({max_passos}) atingido sem resposta final"
    return res
