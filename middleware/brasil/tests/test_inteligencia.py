"""FR-024–FR-035: notícias, verificação, orquestração trocável, chat, matching, otimização, previsões, fila."""
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import yaml

from middleware.brasil import assistentes, ingestao, noticias, orquestracao
from middleware.brasil.orquestracao.claude import ClaudeProvedor
from middleware.brasil.orquestracao.local import LocalProvedor


def como(uid) -> dict:
    """Cabeçalho de identidade que o encaminhador do frontend manda (ADR 0004)."""
    return {"X-Brasil-Usuario": str(uid)}

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
AGORA = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
DOMINIOS = noticias.carregar_fontes()["dominios"]


def item(titulo, link="https://agenciabrasil.ebc.com.br/geral/noticia/2026-10/x", resumo="", quando="2026-10-16T09:00:00+00:00"):
    return {"titulo": titulo, "resumo": resumo, "link": link, "publicado_em": quando, "fonte": "teste"}


def ev(id_, lat, lon, sev=3, fonte="cemaden", tipo="meteorological", **kw):
    return {"id": id_, "title": id_, "lat": lat, "lon": lon, "severity": sev, "crisis_type": tipo, "source": fonte, **kw}


# AC-024.1
def test_ac_024_1_noticia_de_petropolis_vira_crise_nao_verificada_e_site_fora_da_lista_e_ignorado():
    itens = [item("Deslizamento deixa desalojados em Petrópolis (RJ)"),
             item("Deslizamento deixa desalojados em Teresópolis (RJ)", link="https://blog-qualquer.com.br/x")]
    [e] = noticias.extrair(itens, DOMINIOS, AGORA)
    assert e["municipio_ibge"] == 3303906 and e["crisis_type"] == "geological"
    assert e["verificacao"] == "nao_verificada" and e["severity"] <= 3 and e["link_fonte"].startswith("https://agenciabrasil")
    assert e["expira_em"].startswith("2026-10-23")


def test_fr024_regras_de_municipio_e_tipo():
    assert noticias.municipio_no_texto("Enchente deixa desabrigados no Rio Grande do Sul") is None
    assert noticias.municipio_no_texto("Chuva forte alaga ruas e deixa desabrigados em Bonito (MS)") == 5002209
    assert noticias.extrair([item("Prefeitura anuncia obras em Curitiba")], DOMINIOS, AGORA) == []  # sem desastre
    assert noticias.extrair([item("Temporal em Curitiba", resumo="sem relato de estragos")], DOMINIOS, AGORA) == []  # sem impacto


def test_fr024_feed_real_da_agencia_brasil_e_lista_de_fontes():
    import br_noticias
    itens = br_noticias.ler_feed(open(os.path.join(FIXTURES, "agenciabrasil.xml"), "rb").read(), "ab")
    assert all(i["link"].startswith("http") for i in itens)
    evs = noticias.extrair(itens, DOMINIOS, AGORA)
    assert all(e["severity"] <= 3 and e["verificacao"] == "nao_verificada" for e in evs)
    fontes = noticias.carregar_fontes()
    assert len(fontes["feeds"]) >= 3 and noticias.dominio_permitido("https://defesacivil.rs.gov.br/x", fontes["dominios"])
    assert not noticias.dominio_permitido("https://gov.br.golpe.com/x", fontes["dominios"])


def test_cfg008_lista_invalida_impede_subida(tmp_path):
    from middleware.brasil.config import ConfigInvalida
    p = tmp_path / "f.yaml"
    p.write_text(yaml.safe_dump({"feeds": [{"nome": "x", "url": "ftp://x"}], "dominios": ["a.br"]}))
    with pytest.raises(ConfigInvalida, match="feed 1 tem URL inválida"):
        noticias.carregar_fontes(str(p))


def test_fr024_noticia_coberta_por_api_e_descartada(api):
    _, rotas = api
    ingestao.executar(rotas.CFG, fontes={"cemaden": lambda: [ev("cemaden-p", -22.5, -43.18, tipo="geological", municipio_ibge=3303906)]}, agora=AGORA)
    evs = noticias.coletar(rotas.CFG, buscar=lambda feeds: [item("Deslizamento deixa desalojados em Petrópolis (RJ)")], agora=AGORA)
    assert evs == []


def test_fr024_noticia_ja_gravada_com_id_antigo_mantem_o_id_e_a_nova_usa_sha256(api):
    import hashlib
    _, rotas = api
    novo = noticias.extrair([item("Deslizamento deixa mortos em Petrópolis (RJ)")], DOMINIOS, AGORA)[0]
    assert novo["id"] == "noticia-" + hashlib.sha256(novo["link_fonte"].encode()).hexdigest()[:12]
    antigo = {**novo, "id": "noticia-aaaaaaaaaaaa"}  # o formato SHA-1 que já pode estar no banco
    ingestao.executar(rotas.CFG, fontes={"noticias": lambda: [antigo]}, agora=AGORA)
    evs = noticias.coletar(rotas.CFG, buscar=lambda feeds: [item("Deslizamento deixa mortos em Petrópolis (RJ)")], agora=AGORA)
    assert [e["id"] for e in evs] == ["noticia-aaaaaaaaaaaa"]  # mesmo link: mantém o ID gravado
    outra = item("Deslizamento deixa mortos em Teresópolis (RJ)", link="https://agenciabrasil.ebc.com.br/geral/noticia/2026-10/outra")
    [e2] = noticias.coletar(rotas.CFG, buscar=lambda feeds: [outra], agora=AGORA)
    assert e2["id"] == "noticia-" + hashlib.sha256(outra["link"].encode()).hexdigest()[:12]  # link novo: SHA-256


def gravar_noticia(cfg, sev=3):
    e = noticias.extrair([item("Deslizamento deixa mortos em Petrópolis (RJ)")], DOMINIOS, AGORA)[0]
    e["severity"] = 5  # mesmo que venha mais alto, o teto é 3
    ingestao.executar(cfg, fontes={"noticias": lambda: [e]}, agora=AGORA)
    return e["id"]


# AC-025.1
def test_ac_025_1_admin_confirma_noticia_e_ela_perde_selo_e_teto(api):
    cli, rotas = api
    cid = gravar_noticia(rotas.CFG)
    [c] = [x for x in ingestao.crises_ativas(rotas.CFG, AGORA) if x["id"] == cid]
    assert c["verificacao"] == "nao_verificada" and c["severity"] == 3
    admin = cli.post("/brasil/dev/usuario/admin").json()["id"]
    vol = cli.post("/brasil/dev/usuario/voluntario").json()["id"]
    assert cli.put(f"/brasil/crises/{cid}/verificacao", json={"acao": "confirmar"}, headers=como(vol)).status_code == 403
    r = cli.put(f"/brasil/crises/{cid}/verificacao", json={"acao": "confirmar", "severity": 5}, headers=como(admin)).json()
    assert r["verificacao"] == "verificada" and r["severity"] == 5 and r["expira_em"] is None
    gravar_noticia(rotas.CFG)  # nova coleta não desfaz a decisão do admin
    [c] = [x for x in ingestao.crises_ativas(rotas.CFG, AGORA + timedelta(days=10)) if x["id"] == cid]
    assert c["verificacao"] == "verificada" and c["severity"] == 5


def test_fr025_descartada_sai_do_mapa_e_nao_verificada_expira_em_7_dias(api):
    cli, rotas = api
    cid = gravar_noticia(rotas.CFG)
    assert [c["id"] for c in cli.get("/brasil/crises/nao-verificadas", headers=como(cli.post("/brasil/dev/usuario/admin").json()["id"])).json()] == [cid]
    assert cid not in [c["id"] for c in ingestao.crises_ativas(rotas.CFG, AGORA + timedelta(days=8))]
    admin = cli.post("/brasil/dev/usuario/admin").json()["id"]
    cli.put(f"/brasil/crises/{cid}/verificacao", json={"acao": "descartar"}, headers=como(admin))
    assert cid not in [c["id"] for c in ingestao.crises_ativas(rotas.CFG, AGORA)]


# AC-027.1
def test_ac_027_1_brasil_orchestrator_lista_os_3_colaboradores():
    raiz = os.path.join(os.path.dirname(__file__), "..", "..", "..", "agents")
    d = yaml.safe_load(open(os.path.join(raiz, "brasil_orchestrator.yaml"), encoding="utf-8"))
    assert d["collaborators"] == ["monitoring_agent", "classification_agent", "brasil_news_agent"]
    n = yaml.safe_load(open(os.path.join(raiz, "brasil_news_agent.yaml"), encoding="utf-8"))
    assert n["tools"] == ["br_noticias", "br_salvar_eventos"]


class ClienteFalso:
    """Imita client.beta.messages.create: 1º turno pede a ferramenta, 2º termina."""
    def __init__(self, recusar=False):
        self.chamadas = []
        self.recusar = recusar
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.chamadas.append(kw)
        if self.recusar:
            return SimpleNamespace(stop_reason="refusal", content=[])
        if "tools" in kw and len(self.chamadas) == 1:
            uso = SimpleNamespace(type="tool_use", id="t1", name="executar_ingestao", input={"fontes": ["cemaden"]})
            return SimpleNamespace(stop_reason="tool_use", content=[uso])
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Feito.")])


# AC-028.1
def test_ac_028_1_local_e_claude_devolvem_o_mesmo_formato_de_relatorio(api):
    _, rotas = api
    fontes = {"cemaden": lambda: [ev("cemaden-1", -30.03, -51.22)]}
    loc = orquestracao.executar(rotas.CFG, "brasil_orchestrator", provedor=LocalProvedor(rotas.CFG, fontes=fontes))
    cli = ClienteFalso()
    cla = orquestracao.executar(rotas.CFG, "brasil_orchestrator", provedor=ClaudeProvedor(rotas.CFG, cliente=cli, fontes=fontes))
    assert cla.provedor == "claude" and loc.provedor == "local"
    assert set(loc.dados) == set(cla.dados) and cla.dados["fontes"] == loc.dados["fontes"] == {"cemaden": {"ok": True, "eventos": 1}}
    primeira = cli.chamadas[0]
    assert primeira["model"] == "claude-sonnet-5-5" and primeira["tools"][0]["strict"] is True
    assert "tool_choice" not in primeira and primeira["fallbacks"] == "default"
    assert "Crisis Monitor" in primeira["system"] or "Dash Brasil" in primeira["system"]


# AC-029.1
def test_ac_029_1_claude_sem_chave_cai_para_local_e_avisa(api, monkeypatch, capsys):
    _, rotas = api
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fontes = {"cemaden": lambda: [ev("cemaden-1", -30.03, -51.22)]}
    r = orquestracao.executar(rotas.CFG, "brasil_orchestrator", provedor=ClaudeProvedor(rotas.CFG, fontes=fontes),
                              local=LocalProvedor(rotas.CFG, fontes=fontes))
    assert r.provedor == "local" and r.dados["gravadas"] == 1
    assert "claude indisponível: sem ANTHROPIC_API_KEY; usando local" in capsys.readouterr().out
    assert r.avisos == ["claude indisponível: sem ANTHROPIC_API_KEY; usando local"]


def test_fr029_recusa_e_watsonx_sem_credencial_tambem_caem_para_local(api, monkeypatch):
    from middleware.brasil.orquestracao.watsonx import WatsonxProvedor
    _, rotas = api
    ctx = {"plano": {}}
    r = orquestracao.executar(rotas.CFG, "assistant_agent", "plano", ctx, provedor=ClaudeProvedor(rotas.CFG, cliente=ClienteFalso(recusar=True)))
    assert r.provedor == "local" and "recusou" in r.avisos[0]
    monkeypatch.delenv("WO_API_KEY", raising=False)
    r = orquestracao.executar(rotas.CFG, "assistant_agent", "plano", ctx, provedor=WatsonxProvedor(rotas.CFG))
    assert r.provedor == "local" and "sem WO_API_KEY" in r.avisos[0]


def test_fr028_provedores_registrados_batem_com_a_config():
    from middleware.brasil.config import ORQUESTRADORES
    assert set(orquestracao.PROVEDORES) == set(ORQUESTRADORES)


def preparar(cli, rotas):
    fontes = {"cemaden": lambda: [ev("cemaden-poa", -30.03, -51.22, 4), ev("cemaden-sb", -28.75, -55.8, 3)],
              "inpe": lambda: [ev("inpe-am", -3.2, -52.2, 5, fonte="inpe", tipo="wildfire", municipio_ibge=1500602,
                                 visto_em=AGORA.isoformat())]}
    ingestao.executar(rotas.CFG, fontes=fontes, agora=AGORA)
    vol = cli.post("/brasil/dev/usuario/voluntario").json()["id"]  # Porto Alegre, primeiros socorros + logística
    ong = cli.post("/brasil/dev/usuario/ong").json()["id"]
    return vol, ong


# AC-030.1
def test_ac_030_1_chat_do_voluntario_recomenda_crises_proximas_compativeis(api):
    cli, rotas = api
    vol, _ = preparar(cli, rotas)
    r = cli.post("/brasil/chat", json={"mensagem": "onde posso ajudar?"}, headers=como(vol)).json()
    ids = [c["id"] for c in r["dados"]["crises"]]
    assert r["provedor"] == "local" and ids[0] == "cemaden-poa" and len(ids) <= 10
    dist = [c["distancia_km"] for c in r["dados"]["crises"]]
    assert dist == sorted(dist) and "Quero ajudar" in r["texto"]


# AC-031.1
def test_ac_031_1_chat_da_ong_monta_o_plano_estruturado(api):
    cli, rotas = api
    _, ong = preparar(cli, rotas)
    r = cli.post("/brasil/chat", json={"mensagem": "plano", "crisis_id": "cemaden-sb"}, headers=como(ong)).json()
    for parte in ("Resumo da necessidade", "Habilidades necessárias", "Número de voluntários recomendado", "Urgência", "Descrição da campanha"):
        assert parte in r["texto"]


# AC-032.1
def test_ac_032_1_matching_so_com_voluntarios_no_brasil(api):
    cli, rotas = api
    _, ong = preparar(cli, rotas)
    conn = sqlite3.connect(rotas.CFG.db_path)
    for i, (lat, lon) in enumerate([(-30.05, -51.2), (-29.7, -51.1), (-31.7, -52.3), (-34.6, -58.38)]):  # 3 RS, 1 Buenos Aires
        conn.execute("INSERT INTO users (email, password_hash, role, name, skills, lat, lon, radius_km) VALUES (?,?,?,?,?,?,?,?)",
                     (f"m{i}@t.br", "x", "volunteer", f"M{i}", '["resgate"]', lat, lon, 1500))
    conn.commit(); conn.close()
    res = cli.get("/brasil/crises/cemaden-poa/matching", headers=como(ong)).json()
    nomes = [m["name"] for m in res]
    assert "M3" not in nomes and {"M0", "M1", "M2"} <= set(nomes)
    assert [m["score"] for m in res] == sorted([m["score"] for m in res], reverse=True)


# AC-035.1
def test_ac_035_1_notificacoes_vao_para_a_fila(api):
    cli, rotas = api
    _, ong = preparar(cli, rotas)
    conn = sqlite3.connect(rotas.CFG.db_path)
    for i in range(3):
        conn.execute("INSERT INTO users (email, password_hash, role, name, skills, lat, lon, radius_km) VALUES (?,?,?,?,?,?,?,?)",
                     (f"n{i}@t.br", "x", "volunteer", f"N{i}", '["resgate"]', -30.0, -51.2, 1000))
    conn.execute("UPDATE users SET available=0 WHERE email='voluntario@teste.brasil'")
    conn.commit(); conn.close()
    r = cli.post("/brasil/crises/cemaden-sb/notificar", json={"limite": 3}, headers=como(ong)).json()
    assert r["modo"] == "fila" and r["matches"] == 3 and r["enfileiradas"] == 3 and r["enviadas"] == 0  # sev 3: só Telegram
    assert len(cli.get("/brasil/notificacoes", headers=como(cli.post("/brasil/dev/usuario/admin").json()["id"])).json()) == 3


# AC-033.1
def test_ac_033_1_distribuicao_aponta_lacuna_redundancia_e_sugestao(api):
    cli, rotas = api
    vol, ong = preparar(cli, rotas)
    conn = sqlite3.connect(rotas.CFG.db_path)
    ids = []
    for i in range(10):
        ids.append(conn.execute("INSERT INTO users (email, password_hash, role, name, lat, lon) VALUES (?,?,?,?,?,?)",
                                (f"d{i}@t.br", "x", "volunteer", f"D{i}", -28.7, -55.8)).lastrowid)
    conn.commit(); conn.close()
    cid = cli.post("/brasil/campanhas", json={"title": "Apoio SB", "crisis_id": "cemaden-sb", "target_volunteers": 4}, headers=como(ong)).json()["id"]
    for v in ids:
        cli.post(f"/brasil/campanhas/{cid}/voluntarios", json={"volunteer_id": v}, headers=como(ong))
    d = cli.get("/brasil/distribuicao", headers=como(cli.post("/brasil/dev/usuario/admin").json()["id"])).json()
    assert [x["crisis_id"] for x in d["redundancias"]] == ["cemaden-sb"]
    assert "cemaden-poa" in [x["crisis_id"] for x in d["lacunas"]]  # sev 4 sem ninguém
    assert any(s["de"] == "cemaden-sb" and s["para"] == "cemaden-poa" for s in d["sugestoes"])


# AC-034.1
def test_ac_034_1_altamira_com_4_dias_de_queimada_aparece_nas_previsoes(api):
    cli, rotas = api
    for dia in range(4):
        t = AGORA - timedelta(days=dia * 3)
        ingestao.executar(rotas.CFG, fontes={"inpe": lambda t=t: [ev("inpe-1500602", -3.2, -52.2, 4, fonte="inpe", tipo="wildfire",
                                                                     municipio_ibge=1500602, visto_em=t.isoformat())]}, agora=t)
    prev = assistentes.previsoes(rotas.CFG, agora=AGORA)
    assert [(p["municipio"], p["tipo"], p["dias_com_crise"]) for p in prev] == [("Altamira", "wildfire", 4)]
    r = cli.get("/brasil/previsoes", headers=como(cli.post("/brasil/dev/usuario/admin").json()["id"])).json()
    assert r["provedor"] == "local"
