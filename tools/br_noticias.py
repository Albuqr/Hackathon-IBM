import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests
from ibm_watsonx_orchestrate.agent_builder.tools import tool

# Palavras que indicam desastre ou crise humanitária em notícia brasileira (sem acento, minúsculas).
PALAVRAS = (
    "deslizamento", "desabamento", "enchente", "alagamento", "inundacao", "transbordou", "cheia",
    "desabrigad", "desalojad", "deslocad", "evacua", "soterrad", "temporal", "tempestade", "vendaval",
    "granizo", "ciclone", "tornado", "seca", "estiagem", "queimada", "incendio florestal", "incendio em vegetacao",
    "rompimento de barragem", "barragem", "surto", "epidemia", "estado de calamidade", "situacao de emergencia",
    "defesa civil",
)


def sem_acento(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


def ler_feed(conteudo: bytes, fonte: str) -> list[dict]:
    """Itens de um RSS 2.0 (título, link, data, resumo) que mencionam desastre ou crise."""
    if conteudo.startswith(b"\xef\xbb\xbf"):
        conteudo = conteudo[3:]
    raiz = ET.fromstring(conteudo)
    local = lambda tag: tag.rsplit("}", 1)[-1]  # RSS 2.0 sem namespace e RSS 1.0 (RDF) com namespace

    def campo(it, *nomes):
        for filho in it:
            if local(filho.tag) in nomes and (filho.text or "").strip():
                return filho.text.strip()
        return ""

    itens = []
    for it in (e for e in raiz.iter() if local(e.tag) == "item"):
        titulo = campo(it, "title")
        resumo = campo(it, "description")
        texto = sem_acento(f"{titulo} {resumo}")
        if not any(p in texto for p in PALAVRAS):
            continue
        quando = None
        data = campo(it, "pubDate", "date")
        try:
            quando = parsedate_to_datetime(data).isoformat()
        except (TypeError, ValueError):
            quando = data or None  # RSS 1.0 traz dc:date em ISO 8601
        itens.append({"titulo": titulo, "resumo": resumo[:600], "link": campo(it, "link") or it.get(
            "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", ""),
                      "publicado_em": quando, "fonte": fonte})
    return itens


@tool
def br_noticias(feeds: list[str]) -> list[dict]:
    """Lê feeds RSS de fontes confiáveis e devolve notícias sobre desastres e crises no Brasil.

    Args:
        feeds: URLs dos feeds RSS a ler (somente os da lista aprovada de fontes).
    Returns:
        Lista de notícias com titulo, resumo, link, publicado_em e fonte; erros vêm como {"error", "source"}.
    """
    saida = []
    for url in feeds:
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (crisis-monitor-brasil)"}, timeout=30)
            r.raise_for_status()
            saida.extend(ler_feed(r.content, url))
        except Exception as e:
            saida.append({"error": str(e), "source": url})
    return saida
