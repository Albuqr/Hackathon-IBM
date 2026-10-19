"""Campanha guiada: plano, matching com motivos, convite que notifica e próximo passo (redesign em etapas)."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from middleware.brasil import assistentes

from .test_campanhas import campanha, como, preparar

BASE = {"crise_ativa": True, "sev_atual": 4, "sev_inicio": 4, "meta": 10, "confirmados": 2, "aguardando": 2,
        "sem_resposta": [], "recomendados": [], "descobertas": []}


@pytest.mark.parametrize("muda, tipo", [
    ({"crise_ativa": False, "sev_atual": 5, "sev_inicio": 3}, "crise_saiu"),
    ({"sev_atual": 5, "sev_inicio": 3, "meta": 20}, "agravou"),
    ({"recomendados": [{"volunteer_id": 7}]}, "faltam"),
    ({}, "faltam"),
    ({"aguardando": 8, "sem_resposta": [{"volunteer_id": 1, "name": "Ana"}]}, "sem_resposta"),
    ({"confirmados": 10, "aguardando": 0}, "completa"),
    ({"aguardando": 8}, "aguardar"),
])
def test_proximo_passo_segue_a_ordem_de_prioridade(muda, tipo):
    assert assistentes.proximo_passo(BASE | muda)["tipo"] == tipo


def test_agravou_so_quando_a_sugestao_passa_a_meta():
    # severidade subiu, mas a meta já cobre o sugerido para a nova severidade: segue para o próximo critério
    assert assistentes.proximo_passo(BASE | {"sev_atual": 5, "sev_inicio": 3, "meta": 40})["tipo"] == "faltam"
    p = assistentes.proximo_passo(BASE | {"sev_atual": 5, "sev_inicio": 3})
    assert p["meta_sugerida"] == 40 and "de 3 para 5" in p["texto"]


def test_faltam_convida_no_maximo_o_que_falta_e_cita_habilidade_descoberta():
    recs = [{"volunteer_id": i} for i in range(20)]
    p = assistentes.proximo_passo(BASE | {"recomendados": recs, "descobertas": ["abrigo"]})
    assert p["acao"] == "convidar" and len(p["volunteer_ids"]) == 6 and "abrigo" in p["texto"]


def test_cobertura_conta_pessoas_por_habilidade_sem_meta_rigida():
    pessoas = [{"status": "confirmed", "skills": ["Resgate", "logística"]}, {"status": "selected", "skills": ["resgate"]},
               {"status": "declined", "skills": ["abrigo"]}]
    cob = {c["habilidade"]: c for c in assistentes.cobertura(["resgate", "abrigo", "logistica"], pessoas)}
    assert cob["resgate"] == {"habilidade": "resgate", "confirmados": 1, "aguardando": 1}
    assert cob["abrigo"]["confirmados"] == 0 and cob["abrigo"]["aguardando"] == 0  # recusa não cobre
    assert cob["logistica"]["confirmados"] == 1  # sem acento casa
    assert all("alvo" not in c for c in cob.values())


def test_plano_da_crise_traz_sugestao_e_campanha_da_ong(api):
    cli, rotas = api
    ong, vol, _ = preparar(cli, rotas)
    r = cli.get("/brasil/crises/cemaden-sb/plano", headers=como(ong)).json()
    assert r["voluntarios"] == 20 and r["urgencia"] == "alta" and r["habilidades"]
    assert r["minha_campanha"] is None and r["campanhas_ativas"] == 0
    cid = campanha(cli, ong).json()["id"]
    r = cli.get("/brasil/crises/cemaden-sb/plano", headers=como(ong)).json()
    assert r["minha_campanha"]["id"] == cid and r["campanhas_ativas"] == 1
    assert cli.get("/brasil/crises/cemaden-sb/plano", headers=como(vol)).status_code == 403
    assert cli.get("/brasil/crises/nao-existe/plano", headers=como(ong)).status_code == 404


def test_matching_explica_o_score_e_aceita_habilidades_do_plano(api):
    cli, rotas = api
    ong, _, extras = preparar(cli, rotas, n_vol=2)
    r = cli.get("/brasil/crises/cemaden-sb/matching", params={"habilidades": "resgate,abrigo"}, headers=como(ong)).json()
    v = next(m for m in r if m["volunteer_id"] == extras[0])
    assert v["habilidades_comuns"] == ["resgate"] and v["historico"] is False and v["avisado_24h"] is False
    r2 = cli.get("/brasil/crises/cemaden-sb/matching", params={"habilidades": "cozinha"}, headers=como(ong)).json()
    assert next(m for m in r2 if m["volunteer_id"] == extras[0])["habilidades_comuns"] == []


def test_publicar_com_convidados_grava_convites_e_manda_a_mensagem_da_previa(api):
    cli, rotas = api
    ong, vol, extras = preparar(cli, rotas, n_vol=2)
    previa = cli.post("/brasil/convites/previa", headers=como(ong), json={
        "crisis_id": "cemaden-sb", "title": "Apoio em São Borja", "urgency": "alta", "skills_needed": ["logística"],
        "volunteer_id": extras[0]}).json()
    assert "Apoio em São Borja" in previa["texto"] and "ONG Brasil Solidário" in previa["texto"] and previa["canal"] == "fila"
    c = campanha(cli, ong, convidados=[extras[0], extras[1], extras[0], ong]).json()
    assert c["convites"]["convidados"] == 2  # repetido e não-voluntário ficam de fora
    conn = sqlite3.connect(rotas.CFG.db_path)
    msgs = dict(conn.execute("SELECT user_id, mensagem FROM notificacoes_pendentes WHERE canal='telegram'").fetchall())
    conn.close()
    assert msgs[extras[0]] == previa["texto"]
    assert {x["volunteer_id"] for x in cli.get(f"/brasil/campanhas/{c['id']}/voluntarios", headers=como(ong)).json()} == set(extras)


def test_convidar_varios_pula_quem_ja_esta_e_reenviar_so_alcanca_pendentes(api):
    cli, rotas = api
    ong, vol, extras = preparar(cli, rotas, n_vol=2)
    cid = campanha(cli, ong, convidados=[extras[0]]).json()["id"]
    cv = cli.get(f"/brasil/voluntario/{vol}/campanhas", headers=como(vol)).json()
    assert cv == []
    r = cli.post(f"/brasil/campanhas/{cid}/convites", json={"volunteer_ids": [extras[0], vol]}, headers=como(ong)).json()
    assert r["convidados"] == 1  # extras[0] já tinha convite
    cv_id = cli.get(f"/brasil/voluntario/{vol}/campanhas", headers=como(vol)).json()[0]["cv_id"]
    cli.put(f"/brasil/convites/{cv_id}", json={"status": "confirmed"}, headers=como(vol))
    r = cli.post(f"/brasil/campanhas/{cid}/convites", json={"volunteer_ids": [extras[0], vol], "reenviar": True}, headers=como(ong)).json()
    assert r["convidados"] == 1  # só quem não respondeu
    assert cli.post(f"/brasil/campanhas/{cid}/convites", json={"volunteer_ids": [vol]}, headers=como(vol)).status_code == 403


def test_situacao_mostra_funil_cobertura_e_proximo_passo(api):
    cli, rotas = api
    ong, vol, extras = preparar(cli, rotas, n_vol=3)
    cid = campanha(cli, ong, skills_needed=["resgate", "abrigo"], target_volunteers=10, convidados=[extras[0]]).json()["id"]
    s = cli.get(f"/brasil/campanhas/{cid}/situacao", headers=como(ong)).json()
    assert s["funil"] == {"meta": 10, "convidados": 1, "confirmados": 0, "aguardando": 1, "recusaram": 0, "sem_resposta": 0}
    cob = {c["habilidade"]: c for c in s["cobertura"]}
    assert cob["resgate"]["aguardando"] == 1 and cob["abrigo"] == {"habilidade": "abrigo", "confirmados": 0, "aguardando": 0}
    p = s["proximo_passo"]
    assert p["tipo"] == "faltam" and "abrigo" in p["texto"] and extras[0] not in p["volunteer_ids"]
    assert set(p["volunteer_ids"]) <= {r["volunteer_id"] for r in s["recomendados"]}

    # convite antigo sem resposta vira "reenviar" quando a meta já está coberta por convites
    cli.put(f"/brasil/campanhas/{cid}", json={"target_volunteers": 1}, headers=como(ong))
    conn = sqlite3.connect(rotas.CFG.db_path)
    conn.execute("UPDATE campaign_volunteers SET added_at=? WHERE campaign_id=?",
                 ((datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(), cid))
    conn.commit(); conn.close()
    assert cli.get(f"/brasil/campanhas/{cid}/situacao", headers=como(ong)).json()["proximo_passo"]["acao"] == "reenviar"


def test_crise_que_saiu_do_mapa_pede_encerrar_e_encerrar_avisa_confirmados(api):
    cli, rotas = api
    ong, vol, _ = preparar(cli, rotas)
    cid = campanha(cli, ong, convidados=[vol]).json()["id"]
    cv_id = cli.get(f"/brasil/voluntario/{vol}/campanhas", headers=como(vol)).json()[0]["cv_id"]
    cli.put(f"/brasil/convites/{cv_id}", json={"status": "confirmed"}, headers=como(vol))
    conn = sqlite3.connect(rotas.CFG.db_path)
    conn.execute("UPDATE crises SET expira_em='2000-01-01T00:00:00+00:00' WHERE id='cemaden-sb'")
    conn.commit()
    assert cli.get(f"/brasil/campanhas/{cid}/situacao", headers=como(ong)).json()["proximo_passo"]["tipo"] == "crise_saiu"
    cli.put(f"/brasil/campanhas/{cid}", json={"status": "closed"}, headers=como(ong))
    cli.put(f"/brasil/campanhas/{cid}", json={"status": "closed"}, headers=como(ong))  # de novo: não avisa duas vezes
    avisos = conn.execute("SELECT COUNT(*) FROM notificacoes_pendentes WHERE user_id=? AND mensagem LIKE '%encerrou%'", (vol,)).fetchone()[0]
    conn.close()
    assert avisos == 1
    assert cli.get(f"/brasil/campanhas/{cid}/situacao", headers=como(ong)).json()["proximo_passo"]["tipo"] == "encerrada"


def test_painel_traz_proximo_passo_e_crises_sem_gente_perto(api):
    cli, rotas = api
    ong, vol, _ = preparar(cli, rotas)
    p = cli.get(f"/brasil/ong/{ong}/painel", headers=como(ong)).json()
    assert [l["crisis_id"] for l in p["lacunas_perto"]] == ["cemaden-sb"]  # severidade 4 sem ninguém
    assert p["lacunas_perto"][0]["distancia_km"] > 0 and p["lacunas_perto"][0]["crisis_type"] == "meteorological"
    campanha(cli, ong)
    p = cli.get(f"/brasil/ong/{ong}/painel", headers=como(ong)).json()
    assert p["lacunas_perto"] == []  # a ONG já tem campanha lá
    assert p["campanhas"][0]["proximo_passo"]["tipo"] in ("faltam", "aguardar")
    assert cli.get("/brasil/distribuicao", headers=como(ong)).status_code == 200
    assert cli.get("/brasil/distribuicao", headers=como(vol)).status_code == 403
