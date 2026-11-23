"""Parsers dos fetch_* de tools/ contra fixtures gravadas (sem rede: requests.get é substituído).

Fixtures em middleware/tests/fixtures/: `.real.` = recorte de resposta real gravada em 2026-11-23 (com a
primeira entrada repetida para testar duplicata); `.sintetica.` = construída à mão (ReliefWeb exigiu appname).
Os arquivos de tools/ não são alterados; o decorador do watsonx é contornado por agentes._carregar_ferramenta.
"""
import json
from pathlib import Path

import pytest
import requests

from middleware import agentes
from middleware.gravacao import TIPOS_CRISE

FX = Path(__file__).parent / "fixtures"


class _Resp:
    def __init__(self, texto: str):
        self.content = texto.encode("utf-8")
        self.text = texto

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        pass


def _servir(monkeypatch, arquivo: str, texto: str = None):
    corpo = texto if texto is not None else (FX / arquivo).read_text(encoding="utf-8")
    chamadas = []

    def get(url, **kw):
        chamadas.append((url, kw))
        return _Resp(corpo)
    monkeypatch.setattr(requests, "get", get)
    return chamadas


def _sem_rede(monkeypatch):
    def get(*a, **k):
        raise AssertionError("rede proibida nos testes")
    monkeypatch.setattr(requests, "get", get)


# ---------- USGS (real) ----------

def test_fetch_usgs_campos_e_tipo(monkeypatch):
    _servir(monkeypatch, "usgs_4_5_day.real.geojson")
    ev = agentes._carregar_ferramenta("fetch_usgs")()
    assert len(ev) == 4  # 3 reais + 1 duplicata
    e = ev[0]
    assert e["id"].startswith("usgs-") and e["source"] == "usgs" and e["type"] == "seismic"
    assert -90 <= e["lat"] <= 90 and -180 <= e["lon"] <= 180
    assert 1 <= e["severity"] <= 5 and e["urgency"] in ("immediate", "24h")
    assert all(x["type"] in TIPOS_CRISE for x in ev)


def test_fetch_usgs_duplicata_tem_o_mesmo_id(monkeypatch):
    _servir(monkeypatch, "usgs_4_5_day.real.geojson")
    ids = [e["id"] for e in agentes._carregar_ferramenta("fetch_usgs")()]
    assert ids[0] == ids[-1] and len(set(ids)) == 3  # a tool NÃO deduplica


# ---------- GDACS ----------

def test_fetch_gdacs_com_resposta_real_da_api_nao_parseia(monkeypatch):
    # Descoberta: o endpoint geteventlist/SEARCH devolve GeoJSON, mas a tool lê como XML RSS -> erro.
    _servir(monkeypatch, "gdacs_geteventlist.real.json")
    r = agentes._carregar_ferramenta("fetch_gdacs")()
    assert len(r) == 1 and r[0]["source"] == "gdacs" and "error" in r[0]


def test_fetch_gdacs_rss_real_tipos_e_coordenadas(monkeypatch):
    # O mesmo parser aplicado ao RSS real: tipos mapeiam, mas lat/lon saem 0 porque a tool procura
    # geo:lat direto no item e o RSS real aninha em geo:Point (o _ingest_fallback lê certo).
    _servir(monkeypatch, "gdacs_rss.real.xml")
    ev = agentes._carregar_ferramenta("fetch_gdacs")()
    assert [e["id"] for e in ev] == ["gdacs-EQ1578798", "gdacs-FL1104295", "gdacs-DR1027450", "gdacs-WF1034027",
                                     "gdacs-EQ1578798"]
    assert [e["type"] for e in ev] == ["seismic", "meteorological", "meteorological", "wildfire", "seismic"]
    assert all(e["lat"] == 0.0 and e["lon"] == 0.0 for e in ev)


def test_fetch_gdacs_tipo_desconhecido_vira_unknown_fora_de_tipos_crise(monkeypatch):
    xml = (FX / "gdacs_rss.real.xml").read_text(encoding="utf-8").replace(
        "<gdacs:eventtype>EQ</gdacs:eventtype>", "<gdacs:eventtype>XX</gdacs:eventtype>")
    _servir(monkeypatch, None, xml)
    ev = agentes._carregar_ferramenta("fetch_gdacs")()
    assert ev[0]["type"] == "unknown" and "unknown" not in TIPOS_CRISE  # comportamento publicado, mantido


# ---------- ReliefWeb (sintética) ----------

def test_fetch_reliefweb_campos_e_tipos(monkeypatch):
    chamadas = _servir(monkeypatch, "reliefweb_disasters.sintetica.json")
    ev = agentes._carregar_ferramenta("fetch_reliefweb")(limit=4)
    assert chamadas[0][0] == "https://api.reliefweb.int/v2/disasters"
    assert [e["id"] for e in ev] == ["reliefweb-51001", "reliefweb-51002", "reliefweb-51003", "reliefweb-51001"]
    assert [e["type"] for e in ev] == ["meteorological", "sanitary", "humanitarian", "meteorological"]
    e = ev[0]
    assert (e["country"], e["country_iso3"], e["lat"], e["lon"], e["source"]) == ("Exemplolandia", "EXM", -12.5, 17.25, "reliefweb")
    assert e["raw_description"] == "Flood" and e["date"].startswith("2026-11-20")
    assert all(x["type"] in TIPOS_CRISE for x in ev)


def test_reliefweb_appname_padrao_e_variavel(monkeypatch):
    chamadas = _servir(monkeypatch, "reliefweb_disasters.sintetica.json")
    fetch = agentes._carregar_ferramenta("fetch_reliefweb")
    monkeypatch.delenv("RELIEFWEB_APPNAME", raising=False)
    fetch()
    assert chamadas[-1][1]["params"]["appname"] == "hktn26-crisis"
    monkeypatch.setenv("RELIEFWEB_APPNAME", "app-de-teste")
    fetch()
    assert chamadas[-1][1]["params"]["appname"] == "app-de-teste"


def test_fetch_reliefweb_403_vira_erro_estruturado(monkeypatch):
    class R403(_Resp):
        def raise_for_status(self):
            raise requests.HTTPError("403 Client Error")
    monkeypatch.setattr(requests, "get", lambda *a, **k: R403("{}"))
    r = agentes._carregar_ferramenta("fetch_reliefweb")()
    assert r[0]["source"] == "reliefweb" and "403" in r[0]["error"]
