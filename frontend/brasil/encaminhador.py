"""Encaminhador: a única porta do navegador para a API do Brasil (FR-023, ADR 0004).

O navegador manda POST /brasil/acao/<nome> com {"p": parâmetros do caminho, "q": consulta, "corpo": JSON}.
A tabela POLITICA diz, para cada ação, o método, o caminho na API, quem pode e o tempo limite.
`{eu}` no caminho é sempre o usuário da sessão; a identidade vai em cabeçalho, nunca no corpo.
Ação fora da tabela ou perfil errado → 403 sem chamar a API. A API confere de novo (papel e dono).
"""
import re
from typing import NamedTuple
from urllib.parse import quote

TODOS = ("volunteer", "org", "admin")


class Regra(NamedTuple):
    metodo: str
    caminho: str
    papeis: tuple
    timeout: int = 30


POLITICA: dict[str, Regra] = {
    # mapa e crises
    "crises": Regra("GET", "/crises", TODOS),
    "status_coleta": Regra("GET", "/ingestao/status", TODOS),
    "inscrever": Regra("POST", "/crises/{crisis_id}/inscrever", ("volunteer", "org")),
    "cancelar": Regra("POST", "/crises/{crisis_id}/cancelar", ("volunteer", "org")),
    "minhas_inscricoes": Regra("GET", "/usuarios/{eu}/inscricoes", ("volunteer", "org")),
    # perfil e chat
    "salvar_perfil": Regra("PUT", "/usuarios/{eu}", ("volunteer", "org")),
    "chat": Regra("POST", "/chat", ("volunteer", "org"), 120),
    # voluntário: convites
    "meus_convites": Regra("GET", "/voluntario/{eu}/campanhas", ("volunteer",)),
    "responder_convite": Regra("PUT", "/convites/{cv_id}", ("volunteer",)),
    # ONG: campanhas
    "criar_campanha": Regra("POST", "/campanhas", ("org",)),
    "editar_campanha": Regra("PUT", "/campanhas/{cid}", ("org",)),
    "voluntarios_campanha": Regra("GET", "/campanhas/{cid}/voluntarios", ("org",)),
    "adicionar_voluntario": Regra("POST", "/campanhas/{cid}/voluntarios", ("org",)),
    "remover_voluntario": Regra("DELETE", "/campanhas/{cid}/voluntarios/{vid}", ("org",)),
    "voluntarios_disponiveis": Regra("GET", "/voluntarios/disponiveis", ("org",)),
    "matching": Regra("GET", "/crises/{crisis_id}/matching", ("org", "admin"), 60),
    "notificar": Regra("POST", "/crises/{crisis_id}/notificar", ("org", "admin"), 60),
    "plano": Regra("GET", "/crises/{crisis_id}/plano", ("org", "admin")),
    "campanhas_ong": Regra("GET", "/campanhas", ("org",)),
    "situacao": Regra("GET", "/campanhas/{cid}/situacao", ("org",), 60),
    "convidar": Regra("POST", "/campanhas/{cid}/convites", ("org",), 60),
    "previa_convite": Regra("POST", "/convites/previa", ("org",)),
    # admin
    "atualizar_dados": Regra("POST", "/ingestao", ("admin",), 300),
    "nao_verificadas": Regra("GET", "/crises/nao-verificadas", ("admin",)),
    "verificar": Regra("PUT", "/crises/{crisis_id}/verificacao", ("admin",)),
    "distribuicao": Regra("GET", "/distribuicao", ("org", "admin"), 60),
    "notificacoes": Regra("GET", "/notificacoes", ("admin",)),
}

_PARAM = re.compile(r"\{(\w+)\}")


class Recusa(Exception):
    def __init__(self, status: int, detalhe: str):
        super().__init__(detalhe)
        self.status, self.detalhe = status, detalhe


def montar_caminho(modelo: str, params: dict, eu: int) -> str:
    def troca(m):
        nome = m.group(1)
        if nome == "eu":
            return str(eu)
        valor = params.get(nome)
        if valor is None or str(valor) in ("", ".", ".."):
            raise Recusa(400, f"Parâmetro {nome} inválido")
        return quote(str(valor), safe="")  # nunca deixa escapar do caminho ("/", "..")
    return _PARAM.sub(troca, modelo)


def encaminhar(api, nome: str, papel: str | None, eu: int | None, pedido: dict) -> tuple[int, object]:
    """Aplica a política e chama a API. Devolve (status, json)."""
    if not isinstance(pedido, dict) or any(not isinstance(pedido.get(k) or {}, dict) for k in ("p", "q")):
        raise Recusa(400, "Pedido inválido")
    regra = POLITICA.get(nome)
    if regra is None or eu is None or papel not in regra.papeis:
        raise Recusa(403, "Seu perfil não pode fazer isto")
    caminho = montar_caminho(regra.caminho, pedido.get("p") or {}, eu)
    kw = {}
    if pedido.get("q"):
        kw["params"] = pedido["q"]
    if regra.metodo in ("POST", "PUT") and pedido.get("corpo") is not None:
        kw["json"] = pedido["corpo"]
    return api(regra.metodo, caminho, usuario=eu, timeout=regra.timeout, **kw)
