"""Notícias de fontes confiáveis → crises não verificadas (FR-024, CFG-008).

É o comportamento do `brasil_news_agent` no provedor `local` (sem LLM): lê os feeds da lista
aprovada, aceita só links de domínios da lista, reconhece tipo de desastre e município por regras,
limita a severidade a 3 e descarta o que uma API já cobre no mesmo município e tipo.
"""
import fnmatch
import hashlib
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from urllib.parse import urlparse

import yaml

from . import db, malha
from .config import Config, ConfigInvalida

ARQUIVO = os.path.join(os.path.dirname(__file__), "fontes_noticias.yaml")
VALIDADE = timedelta(days=7)
SEVERIDADE_MAX = 3

TIPOS = [  # (regex sobre texto sem acento, tipo); a primeira que casar define o tipo
    (r"\b(deslizament|desmoronament|soterrad|desabament|rompimento de barragem|movimento de massa)\w*", "geological"),
    (r"\b(enchente|alagament|inundac|temporal|tempestade|vendaval|granizo|ciclone|tornado|transbord|chuvas? fortes?)\w*", "meteorological"),
    (r"\b(queimadas?|incendios? floresta\w*|incendios? em vegetacao|fogo em vegetacao)\b", "wildfire"),
    (r"\b(seca|estiagem)\b", "drought"),
    (r"\b(surto de|epidemia de)\b", "sanitary"),
]
IMPACTO = r"\b(mort|desaparecid|ferid|desabrigad|desalojad|danific|destrui|interditad|evacua|atingid|isolad|alerta|emergencia|calamidade|resgat)\w*"
GRAVE = r"\b(mort[oa]s?|morre\w*|desaparecid|desabrigad|desalojad|calamidade|situacao de emergencia)\w*"
UFS = {
    "AC": "acre", "AL": "alagoas", "AP": "amapa", "AM": "amazonas", "BA": "bahia", "CE": "ceara", "DF": "distrito federal",
    "ES": "espirito santo", "GO": "goias", "MA": "maranhao", "MT": "mato grosso", "MS": "mato grosso do sul",
    "MG": "minas gerais", "PA": "para", "PB": "paraiba", "PR": "parana", "PE": "pernambuco", "PI": "piaui",
    "RJ": "rio de janeiro", "RN": "rio grande do norte", "RS": "rio grande do sul", "RO": "rondonia", "RR": "roraima",
    "SC": "santa catarina", "SP": "sao paulo", "SE": "sergipe", "TO": "tocantins",
}
POPULOSO = 100_000  # sem a UF no texto, só aceita município com pelo menos isso de habitantes


def sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


def carregar_fontes(caminho: str = ARQUIVO) -> dict:
    """Lê e valida a lista de fontes; erro impede a subida, nomeando o arquivo e o problema."""
    try:
        with open(caminho, encoding="utf-8") as fh:
            d = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as e:
        raise ConfigInvalida(f"BRASIL_FONTES_NOTICIAS ({caminho}) não abre: {e}")
    feeds, dominios = d.get("feeds") or [], d.get("dominios") or []
    for i, f in enumerate(feeds, 1):
        u = urlparse(str(f.get("url", "")))
        if u.scheme != "https" or not u.netloc:
            raise ConfigInvalida(f"BRASIL_FONTES_NOTICIAS ({caminho}): feed {i} tem URL inválida: {f.get('url')!r}")
    if not dominios:
        raise ConfigInvalida(f"BRASIL_FONTES_NOTICIAS ({caminho}): lista de domínios vazia")
    return {"feeds": [f["url"] for f in feeds], "dominios": [str(x).lower() for x in dominios]}


def dominio_permitido(link: str, dominios: list[str]) -> bool:
    host = (urlparse(link).hostname or "").lower()
    return any(fnmatch.fnmatchcase(host, p) and host.count(".") == p.count(".") for p in dominios)


@lru_cache(maxsize=1)
def _indice_nomes():
    """nome sem acento → [(código IBGE, UF, população)], e o tamanho máximo de nome em palavras."""
    idx, maior = {}, 1
    for p in malha.carregar().municipios.values():
        nome = sem_acento(p["nome"])
        idx.setdefault(nome, []).append((p["id"], p["uf"], p["pop_2022"]))
        maior = max(maior, len(nome.split()))
    return idx, maior


@lru_cache(maxsize=8192)
def _centro(cod: int):
    m = malha.carregar()
    for f in m.dados["geojson"]["features"]:
        if f["properties"]["id"] == cod:
            g = f["geometry"]
            anel = g["coordinates"][0] if g["type"] == "Polygon" else max((p[0] for p in g["coordinates"]), key=len)
            return sum(p[1] for p in anel) / len(anel), sum(p[0] for p in anel) / len(anel)
    return None


def municipio_no_texto(texto_original: str):
    """Município citado no texto (nome com inicial maiúscula), desempatado pela UF citada."""
    idx, maior = _indice_nomes()
    palavras = re.findall(r"[\wÀ-ÿ'-]+", texto_original)
    norm = sem_acento(texto_original)
    ufs_citadas = {uf for uf, nome in UFS.items() if re.search(rf"\b{nome}\b", norm) or re.search(rf"\b{uf}\b", texto_original)}
    # trechos dentro de um nome de UF mais longo ("Rio Grande" em "Rio Grande do Sul") não são município
    pn = [sem_acento(w) for w in palavras]
    dentro_de_uf = []
    for nome in UFS.values():
        t = nome.split()
        dentro_de_uf += [(i, i + len(t)) for i in range(len(pn) - len(t) + 1) if pn[i:i + len(t)] == t]
    achados = []
    for n in range(maior, 0, -1):
        for i in range(len(palavras) - n + 1):
            trecho = palavras[i:i + n]
            if not trecho[0][:1].isupper():
                continue
            if any(a <= i and i + n <= b and (b - a) > n for a, b in dentro_de_uf):
                continue
            for cod, uf, pop in idx.get(sem_acento(" ".join(trecho)), []):
                achados.append((n, cod, uf, pop))
        if achados:
            break  # prefere o nome mais longo ("São Raimundo Nonato" antes de "Nonato")
    com_uf = [a for a in achados if a[2] in ufs_citadas]
    if com_uf:
        return max(com_uf, key=lambda a: a[3])[1]
    grandes = [a for a in achados if a[3] >= POPULOSO]
    return max(grandes, key=lambda a: a[3])[1] if grandes else None


def extrair(itens: list[dict], dominios: list[str], agora: datetime | None = None) -> list[dict]:
    agora = agora or datetime.now(timezone.utc)
    eventos, vistos = [], set()
    for it in itens:
        if it.get("error") or not dominio_permitido(it.get("link", ""), dominios):
            continue
        texto = f"{it.get('titulo', '')}. {re.sub(r'<[^>]+>', ' ', it.get('resumo', ''))}"
        norm = sem_acento(texto)
        tipo = next((t for rx, t in TIPOS if re.search(rx, norm)), None)
        if not tipo or not re.search(IMPACTO, norm):
            continue
        cod = municipio_no_texto(texto)
        centro = _centro(cod) if cod else None
        if not centro or (cod, tipo) in vistos:
            continue
        vistos.add((cod, tipo))
        publicado = it.get("publicado_em") or agora.isoformat()
        eventos.append({
            "id": "noticia-" + hashlib.sha1(it["link"].encode()).hexdigest()[:12],
            "title": it["titulo"][:200],
            "lat": round(centro[0], 5), "lon": round(centro[1], 5),
            "severity": SEVERIDADE_MAX if re.search(GRAVE, norm) else 2,
            "urgency": "24h", "crisis_type": tipo, "source": "noticias",
            "municipio_ibge": cod, "link_fonte": it["link"], "verificacao": "nao_verificada",
            "visto_em": publicado,
            "expira_em": (datetime.fromisoformat(publicado.replace("Z", "+00:00")) + VALIDADE).isoformat()
            if "T" in publicado else (agora + VALIDADE).isoformat(),
        })
    return eventos


def ja_coberto_por_api(cfg: Config, eventos: list[dict], agora: datetime) -> list[dict]:
    """Remove notícias cujo município e tipo já têm crise ativa vinda de uma API."""
    conn = db.conectar(cfg)
    try:
        cobertos = {(r[0], r[1]) for r in conn.execute(
            """SELECT municipio_ibge, crisis_type FROM crises WHERE source != 'noticias'
               AND (expira_em IS NULL OR expira_em > ?)""", (agora.isoformat(timespec="seconds"),))}
    finally:
        conn.close()
    return [e for e in eventos if (e["municipio_ibge"], e["crisis_type"]) not in cobertos]


def coletar(cfg: Config, buscar=None, agora: datetime | None = None) -> list[dict]:
    """Fonte "noticias" da ingestão no modo local."""
    from .ingestao import _tools, executar_ferramenta
    agora = agora or datetime.now(timezone.utc)
    fontes = carregar_fontes()
    if buscar is None:
        _tools()
        import br_noticias
        itens = executar_ferramenta(br_noticias.br_noticias, feeds=fontes["feeds"])
    else:
        itens = buscar(fontes["feeds"])
    if itens and all(i.get("error") for i in itens):
        return [{"error": itens[0]["error"], "source": "noticias"}]
    return ja_coberto_por_api(cfg, extrair(itens, fontes["dominios"], agora), agora)
