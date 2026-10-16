"""FR-002, FR-003, FR-005, FR-009, FR-010, FR-015, FR-020–FR-023 pela API /brasil."""
import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from middleware.brasil import ingestao

AGORA = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)


def ev(id_, lat, lon, sev=3, fonte="cemaden", **kw):
    return {"id": id_, "title": id_, "lat": lat, "lon": lon, "severity": sev, "crisis_type": "meteorological",
            "source": fonte, **kw}


# AC-002.1
def test_ac_002_1_saude(api):
    cli, _ = api
    r = cli.get("/brasil/saude")
    assert r.status_code == 200 and r.json()["orquestrador"] == "local"


# AC-005.1
def test_ac_005_1_dev_login_cria_os_3_perfis(api):
    cli, _ = api
    papeis = {p: cli.post(f"/brasil/dev/usuario/{p}").json()["role"] for p in ("voluntario", "ong", "admin")}
    assert papeis == {"voluntario": "volunteer", "ong": "org", "admin": "admin"}
    # idempotente
    assert cli.post("/brasil/dev/usuario/ong").json()["id"] == cli.post("/brasil/dev/usuario/ong").json()["id"]


# AC-005.2
def test_ac_005_2_dev_login_desligado_responde_404(api, monkeypatch):
    import importlib
    monkeypatch.delenv("BRASIL_DEV_LOGIN")
    cli, rotas = api
    importlib.reload(rotas)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(rotas.router)
    assert TestClient(app).post("/brasil/dev/usuario/admin").status_code == 404


# AC-003.1
def test_ac_003_1_banco_do_crisis_nao_muda(api, ambiente):
    cli, rotas = api
    crisis = ambiente / "crisis.db"
    antes = hashlib.sha256(crisis.read_bytes()).hexdigest()
    uid = cli.post("/brasil/dev/usuario/voluntario").json()["id"]
    ingestao.executar(rotas.CFG, fontes={"cemaden": lambda: [ev("cemaden-1", -30.03, -51.22)]}, agora=AGORA)
    cli.post("/brasil/crises/cemaden-1/inscrever", json={"user_id": uid})
    cli.put(f"/brasil/usuarios/{uid}", json={"radius_km": 100})
    assert hashlib.sha256(crisis.read_bytes()).hexdigest() == antes
    assert (ambiente / "brasil.db").exists()


# AC-020.1, AC-021.1
def test_ac_020_1_e_ac_021_1_filtra_fora_do_brasil_e_atribui_municipio(api):
    _, rotas = api
    fontes = {"usgs": lambda: [
        {"id": "chile", "title": "Sismo Chile", "lat": -33.45, "lon": -70.66, "severity": 3, "source": "usgs"},
        {"id": "acre", "title": "Sismo Acre", "lat": -8.5, "lon": -71.5, "severity": 2, "source": "usgs"},
    ], "eonet": lambda: [{"id": "df", "title": "Fogo DF", "lat": -15.79, "lon": -47.88, "severity": 2, "source": "eonet"}]}
    rel = ingestao.executar(rotas.CFG, fontes=fontes, agora=AGORA)
    ativas = {c["id"]: c for c in ingestao.crises_ativas(rotas.CFG, AGORA)}
    assert set(ativas) == {"br-acre", "br-df"} and rel["fontes"]["usgs"]["eventos"] == 1
    assert ativas["br-df"]["municipio_ibge"] == 5300108 and ativas["br-df"]["uf"] == "DF"


# AC-022.1
def test_ac_022_1_queimada_sem_foco_ha_49h_sai_do_mapa(api):
    _, rotas = api
    velho = (AGORA - timedelta(hours=49)).isoformat()
    novo = (AGORA - timedelta(hours=2)).isoformat()
    fontes = {"inpe": lambda: [ev("inpe-1500602", -3.2, -52.2, fonte="inpe", municipio_ibge=1500602, visto_em=velho),
                               ev("inpe-5300108", -15.79, -47.88, fonte="inpe", municipio_ibge=5300108, visto_em=novo)]}
    ingestao.executar(rotas.CFG, fontes=fontes, agora=AGORA)
    assert [c["id"] for c in ingestao.crises_ativas(rotas.CFG, AGORA)] == ["inpe-5300108"]


def test_fr022_cemaden_sai_quando_some_da_fonte_e_inmet_no_fim_da_validade(api):
    _, rotas = api
    ingestao.executar(rotas.CFG, fontes={"cemaden": lambda: [ev("cemaden-1", -30.03, -51.22), ev("cemaden-2", -29.7, -53.8)]}, agora=AGORA)
    ingestao.executar(rotas.CFG, fontes={"cemaden": lambda: [ev("cemaden-2", -29.7, -53.8)]}, agora=AGORA + timedelta(minutes=5))
    ids = [c["id"] for c in ingestao.crises_ativas(rotas.CFG, AGORA + timedelta(minutes=6))]
    assert ids == ["cemaden-2"]
    ingestao.executar(rotas.CFG, fontes={"inmet": lambda: [ev("inmet-9", -21, -49, fonte="inmet", expira_em="2026-10-16T10:00:00-03:00")]}, agora=AGORA)
    ativas = lambda t: [c["id"] for c in ingestao.crises_ativas(rotas.CFG, t) if c["source"] == "inmet"]
    assert ativas(AGORA) == ["inmet-9"] and ativas(AGORA + timedelta(hours=2)) == []


# AC-023.1
def test_ac_023_1_fonte_com_falha_nao_derruba_as_outras(api):
    _, rotas = api
    ingestao.executar(rotas.CFG, fontes={"cemaden": lambda: [ev("cemaden-1", -30.03, -51.22)]}, agora=AGORA)

    def quebra():
        raise ConnectionError("CEMADEN fora do ar")

    rel = ingestao.executar(rotas.CFG, fontes={
        "cemaden": quebra,
        "inpe": lambda: [ev("inpe-5300108", -15.79, -47.88, fonte="inpe", municipio_ibge=5300108, visto_em=AGORA.isoformat())],
    }, agora=AGORA + timedelta(minutes=10))
    assert rel["fontes"]["cemaden"]["ok"] is False and rel["fontes"]["inpe"]["ok"] is True
    ids = {c["id"] for c in ingestao.crises_ativas(rotas.CFG, AGORA + timedelta(minutes=11))}
    assert ids == {"cemaden-1", "inpe-5300108"}  # CEMADEN mantém a última coleta boa
    st = {s["fonte"]: s for s in ingestao.status(rotas.CFG)}
    assert st["cemaden"]["ok"] == 0 and "fora do ar" in st["cemaden"]["erro"] and st["cemaden"]["ultimo_ok_em"]


# AC-015.1
def test_ac_015_1_status_por_fonte_pela_api(api):
    cli, rotas = api
    ingestao.executar(rotas.CFG, fontes={"cemaden": lambda: [ev("cemaden-1", -30.03, -51.22)]}, agora=AGORA)
    [s] = cli.get("/brasil/ingestao/status").json()
    assert s["fonte"] == "cemaden" and s["ok"] == 1 and s["eventos"] == 1 and s["tentativa_em"]


# AC-009.1
def test_ac_009_1_inscrever_e_cancelar(api):
    cli, rotas = api
    uid = cli.post("/brasil/dev/usuario/voluntario").json()["id"]
    ingestao.executar(rotas.CFG, fontes={"cemaden": lambda: [ev("cemaden-1", -30.03, -51.22)]})
    assert cli.post("/brasil/crises/cemaden-1/inscrever", json={"user_id": uid}).json()["inscritos"] == 1
    assert [i["id"] for i in cli.get(f"/brasil/usuarios/{uid}/inscricoes").json()] == ["cemaden-1"]
    assert cli.post("/brasil/crises/cemaden-1/cancelar", json={"user_id": uid}).json()["inscritos"] == 0
    assert cli.get(f"/brasil/usuarios/{uid}/inscricoes").json() == []


def test_fr009_admin_nao_se_inscreve(api):
    cli, rotas = api
    uid = cli.post("/brasil/dev/usuario/admin").json()["id"]
    ingestao.executar(rotas.CFG, fontes={"cemaden": lambda: [ev("cemaden-1", -30.03, -51.22)]})
    assert cli.post("/brasil/crises/cemaden-1/inscrever", json={"user_id": uid}).status_code == 403


# AC-010.1
def test_ac_010_1_localizacao_fora_do_brasil_e_recusada(api):
    cli, _ = api
    uid = cli.post("/brasil/dev/usuario/voluntario").json()["id"]
    r = cli.put(f"/brasil/usuarios/{uid}", json={"lat": -34.6, "lon": -58.38})
    assert r.status_code == 422 and r.json()["detail"] == "A localização precisa estar no Brasil"
    assert cli.get(f"/brasil/usuarios/{uid}").json()["lat"] == pytest.approx(-30.0346)


def test_fr010_perfil_salva_habilidades_e_local_no_brasil(api):
    cli, _ = api
    uid = cli.post("/brasil/dev/usuario/voluntario").json()["id"]
    u = cli.put(f"/brasil/usuarios/{uid}", json={"lat": -3.73, "lon": -38.52, "skills": ["resgate", " "], "radius_km": 50}).json()
    assert u["skills"] == ["resgate"] and u["radius_km"] == 50 and u["link_code"]


def test_fr007_voluntarios_por_municipio(api):
    cli, _ = api
    cli.post("/brasil/dev/usuario/voluntario")
    assert cli.get("/brasil/voluntarios/por-municipio").json() == {"4314902": 1}  # Porto Alegre
