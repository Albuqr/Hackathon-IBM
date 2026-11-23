"""Semente de teste (semear_teste.py): abrigos, pessoas e estoque fictícios de gestor e gestor2."""
import importlib

from middleware.brasil import db


def semear():
    import middleware.brasil.rotas as rotas
    importlib.reload(rotas)  # CFG do banco temporário do `ambiente`
    import middleware.brasil.semear_teste as semente
    semente.main()
    return rotas


def contagens(rotas) -> dict:
    conn = db.conectar(rotas.CFG)
    try:
        g = {p: rotas.dev_usuario(p)["id"] for p in ("gestor", "gestor2")}
        n = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
        return {
            "abrigos_gestor": n("SELECT COUNT(*) FROM abrigos WHERE gestor_id=?", g["gestor"]),
            "abrigos_gestor2": n("SELECT COUNT(*) FROM abrigos WHERE gestor_id=?", g["gestor2"]),
            "verificados": n("SELECT COUNT(*) FROM abrigos WHERE verificado=1"),
            "sensiveis": n("SELECT COUNT(*) FROM abrigos WHERE sensivel=1"),
            "pessoas": n("SELECT COUNT(*) FROM abrigados"),
            "presentes": n("SELECT COUNT(*) FROM abrigados WHERE saida_em IS NULL"),
            "familias": n("SELECT COUNT(*) FROM familias"),
            "familia_de_3": n("SELECT COUNT(*) FROM (SELECT familia_id FROM abrigados WHERE familia_id IS NOT NULL "
                              "GROUP BY familia_id HAVING COUNT(*)=3)"),
            "com_cpf": n("SELECT COUNT(*) FROM abrigados WHERE cpf IS NOT NULL"),
            "com_necessidade": n("SELECT COUNT(*) FROM abrigados WHERE necessidades != '[]'"),
            "estoque": n("SELECT COUNT(*) FROM abrigo_itens"),
            "vinculo_poa4": n("SELECT COUNT(*) FROM abrigo_crises WHERE crisis_id='teste-poa-4'"),
            "itens": n("SELECT COUNT(*) FROM itens"),
            # a API recusa chegada em abrigo inativo; a semente grava direto, então confere aqui
            "pessoas_em_inativo": n("SELECT COUNT(*) FROM abrigados p JOIN abrigos a ON a.id=p.abrigo_id WHERE a.ativo=0"),
        }
    finally:
        conn.close()


def test_semente_cria_abrigos_pessoas_e_estoque_ficticios_e_e_idempotente(ambiente, capsys):
    rotas = semear()
    primeira = contagens(rotas)
    assert primeira == {"abrigos_gestor": 1, "abrigos_gestor2": 2, "verificados": 0, "sensiveis": 1,
                        "pessoas": 10, "presentes": 9, "familias": 2, "familia_de_3": 1, "com_cpf": 0,
                        "com_necessidade": 5, "estoque": 8, "vinculo_poa4": 1, "itens": primeira["itens"],
                        "pessoas_em_inativo": 0}
    saida = capsys.readouterr().out
    assert "abrigos: 3" in saida and "pessoas: 10 (9 presentes)" in saida
    conn = db.conectar(rotas.CFG)
    nomes = [r[0] for r in conn.execute("SELECT nome FROM abrigados")] + [r[0] for r in conn.execute("SELECT nome_mae FROM abrigados")]
    conn.close()
    assert not any(nome in saida for nome in nomes)  # o resumo nunca tem nome de pessoa

    semear()
    assert contagens(rotas) == primeira  # segunda rodada recria, não duplica


def test_semente_pela_api_estoque_lotacao_e_busca_sem_verificar(ambiente):
    rotas = semear()
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(rotas.router)
    cli = TestClient(app)
    g1 = {"X-Brasil-Usuario": str(rotas.dev_usuario("gestor")["id"])}
    (abrigo,) = cli.get("/brasil/abrigos", headers=g1).json()
    assert abrigo["verificado"] is False and abrigo["capacidade"] == 60 and abrigo["presentes"] == 5
    assert abrigo["municipio"] == "Porto Alegre" and [c["id"] for c in abrigo["crises"]] == ["teste-poa-4"]
    estoque = {x["nome"]: x["status"] for x in cli.get(f"/brasil/abrigos/{abrigo['id']}/estoque", headers=g1).json()}
    assert estoque["Água"] == "urgente" and estoque["Colchões"] == "sobrando" and estoque["Equipe de saúde"] == "precisa"
    # não verificado: a busca só acha gente dos próprios abrigos
    busca = cli.get("/brasil/abrigados/busca", params={"nome": "exemplo"}, headers=g1).json()
    assert busca["escopo"] == "meus_abrigos" and busca["resultados"]
    assert all(r["meu_abrigo"] for r in busca["resultados"])
