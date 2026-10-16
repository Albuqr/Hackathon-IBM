"""FR-017, FR-018, FR-019 com respostas gravadas (sem rede)."""
import json
import os
from datetime import datetime, timezone

from br_cemaden import converter_alertas
from br_inmet import converter_avisos
from br_inpe_queimadas import agregar_focos, severidade

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

DESDE = datetime(2026, 10, 15, tzinfo=timezone.utc)


def focos(n, cod="1500602", risco="0.5", hora="2026-10-15 12:00:00"):
    return [{"data_hora_gmt": hora, "municipio_id": cod, "lat": "-3.2", "lon": "-52.2", "risco_fogo": risco,
             "municipio": "ALTAMIRA", "estado": "PARÁ"} for _ in range(n)]


# AC-017.1
def test_ac_017_1_altamira_230_focos_risco_alto_vira_severidade_5():
    [ev] = agregar_focos(focos(230, risco="0.9"), DESDE)
    assert ev["crisis_type"] == "wildfire" and ev["severity"] == 5 and ev["municipio_ibge"] == 1500602
    assert "Altamira" in ev["title"]


# AC-017.2
def test_ac_017_2_cinco_focos_risco_baixo_vira_severidade_1():
    [ev] = agregar_focos(focos(5, risco="0.2"), DESDE)
    assert ev["severity"] == 1


def test_fr017_cortes_e_teto():
    assert [severidade(n, 0) for n in (9, 10, 49, 50, 199, 200, 499, 500)] == [1, 2, 2, 3, 3, 4, 4, 5]
    assert severidade(600, 0.95) == 5


def test_fr017_ignora_focos_antes_da_janela():
    assert agregar_focos(focos(3, hora="2026-10-14 23:00:00"), DESDE) == []


def test_fr017_amostra_real_do_inpe():
    import csv
    with open(os.path.join(FIXTURES, "inpe_amostra.csv"), encoding="utf-8") as fh:
        evs = agregar_focos(csv.DictReader(fh), DESDE)
    assert evs and all(1 <= e["severity"] <= 5 and len(str(e["municipio_ibge"])) == 7 for e in evs)


# AC-018.1
def test_ac_018_1_cemaden_sao_borja_risco_hidrologico_alto():
    dados = json.load(open(os.path.join(FIXTURES, "cemaden.json"), encoding="utf-8"))
    evs = {e["municipio_ibge"]: e for e in converter_alertas(dados)}
    sb = evs[4318002]
    assert sb["crisis_type"] == "meteorological" and sb["severity"] == 4 and sb["source"] == "cemaden"


def test_fr018_movimento_de_massa_vira_geological_e_inativo_e_ignorado():
    dados = {"alertas": [
        {"cod_alerta": 1, "evento": "Movimentos de Massa - Muito Alto", "nivel": "Muito Alto", "status": 1,
         "uf": "RJ", "municipio": "PETRÓPOLIS", "codibge": 3303906, "latitude": -22.5, "longitude": -43.2},
        {"cod_alerta": 2, "evento": "Risco Hidrológico - Alto", "nivel": "Alto", "status": 0,
         "uf": "RS", "municipio": "X", "codibge": 4300000, "latitude": -30, "longitude": -51},
    ]}
    [ev] = converter_alertas(dados)
    assert ev["crisis_type"] == "geological" and ev["severity"] == 5


# AC-019.1
def test_ac_019_1_inmet_grande_perigo_no_centroide():
    aviso = {"id_aviso": 9, "id_sequencia": 1, "severidade": "Grande Perigo", "descricao": "Chuvas Intensas",
             "poligono": json.dumps({"type": "Polygon", "coordinates": [[[-50, -20], [-48, -20], [-48, -22], [-50, -22], [-50, -20]]]}),
             "geocodes": "3550308,3304557", "fim": "2026-10-17 10:00", "encerrado": False}
    [ev] = converter_avisos({"hoje": [aviso], "futuro": []})
    assert ev["severity"] == 5 and abs(ev["lat"] + 21) < 1e-6 and abs(ev["lon"] + 49) < 1e-6
    assert ev["municipios_afetados"] == [3550308, 3304557] and ev["expira_em"] == "2026-10-17T10:00:00-03:00"


def test_fr019_amostra_real_do_inmet():
    dados = json.load(open(os.path.join(FIXTURES, "inmet.json"), encoding="utf-8"))
    evs = converter_avisos(dados)
    assert evs and all(e["severity"] in (2, 4, 5) and e["municipios_afetados"] for e in evs)


def test_ferramentas_decoradas_devolvem_lista_pura(monkeypatch):
    """As ferramentas @tool do watsonx 2.8.0 devolvem ToolResponse quando chamadas direto."""
    import br_cemaden
    from middleware.brasil.ingestao import executar_ferramenta
    dados = json.load(open(os.path.join(FIXTURES, "cemaden.json"), encoding="utf-8"))

    class Resp:
        def raise_for_status(self): pass
        def json(self): return dados

    monkeypatch.setattr(br_cemaden.requests, "get", lambda *a, **k: Resp())
    evs = executar_ferramenta(br_cemaden.br_cemaden)
    assert isinstance(evs, list) and evs[0]["source"] == "cemaden"
