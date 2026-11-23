"""FR-004: merge do brasil.db no banco do Crisis."""
import os
import runpy
import sqlite3

import pytest

from middleware.brasil import db
from middleware.brasil.config import carregar
from middleware.brasil.merge_brasil import _preparar_crisis, unir

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@pytest.fixture
def bancos(tmp_path, monkeypatch):
    # banco do Crisis com o esquema real (init_db.py) e o admin padrão (id 1)
    monkeypatch.chdir(tmp_path)
    runpy.run_path(os.path.join(RAIZ, "init_db.py"))
    crisis = str(tmp_path / "data" / "crisis.db")
    c = sqlite3.connect(crisis)
    for i in range(2, 7):
        c.execute("INSERT INTO users (email, password_hash, role, name) VALUES (?,?,?,?)", (f"u{i}@x.org", "h", "volunteer", f"U{i}"))
    c.execute("INSERT INTO users (email, password_hash, role, name) VALUES ('ana@x.org','h','org','Ana Crisis')")  # id 7
    c.execute("INSERT INTO campaigns (org_id, title) VALUES (7, 'Campanha do Crisis')")  # id 1
    c.execute("INSERT INTO crises (id, title, country, lat, lon, severity) VALUES ('usgs-1','Sismo','Chile',-33,-70,3)")
    c.commit(); c.close()

    brasil = str(tmp_path / "data" / "brasil.db")
    monkeypatch.setenv("DB_PATH", crisis)
    monkeypatch.setenv("BRASIL_DB_PATH", brasil)
    db._prontos.clear()
    b = db.conectar(carregar())
    b.execute("INSERT INTO users (email, password_hash, role, name) VALUES ('x@br.org','h','volunteer','X')")   # id 1
    b.execute("INSERT INTO users (email, password_hash, role, name) VALUES ('y@br.org','h','volunteer','Y')")   # id 2
    b.execute("INSERT INTO users (email, password_hash, role, name, org_name) VALUES ('ana@x.org','h','org','Ana','ONG Ana')")  # id 3
    b.execute("INSERT INTO crises (id, title, country, lat, lon, severity, municipio_ibge, uf) VALUES ('cemaden-1','Chuva','Brasil',-30,-51,4,4314902,'RS')")
    b.execute("INSERT INTO campaigns (org_id, title, crisis_id) VALUES (3, 'Campanha da Ana no Brasil', 'cemaden-1')")  # id 1
    b.execute("INSERT INTO campaign_volunteers (campaign_id, volunteer_id, status) VALUES (1, 2, 'confirmed')")
    b.execute("INSERT INTO crisis_associations (crisis_id, user_id, role) VALUES ('cemaden-1', 1, 'volunteer')")
    b.commit(); b.close()
    return crisis, brasil


def linhas(path, sql, *p):
    c = sqlite3.connect(path)
    try:
        return c.execute(sql, p).fetchall()
    finally:
        c.close()


# AC-004.1
def test_ac_004_1_usuario_com_mesmo_email_vira_um_so_e_campanha_aponta_para_ele(bancos):
    crisis, brasil = bancos
    rel = unir(crisis, brasil)
    assert rel["usuarios_unificados"] == 1 and rel["usuarios_novos"] == 2
    assert linhas(crisis, "SELECT id FROM users WHERE email='ana@x.org'") == [(7,)]
    assert linhas(crisis, "SELECT org_id FROM campaigns WHERE title='Campanha da Ana no Brasil'") == [(7,)]


# AC-004.2
def test_ac_004_2_ids_renumerados_sem_mexer_no_crisis(bancos):
    crisis, brasil = bancos
    antes = linhas(crisis, "SELECT id, org_id, title FROM campaigns WHERE id=1")
    unir(crisis, brasil)
    assert linhas(crisis, "SELECT id, org_id, title FROM campaigns WHERE id=1") == antes
    [(novo_id,)] = linhas(crisis, "SELECT id FROM campaigns WHERE title='Campanha da Ana no Brasil'")
    assert novo_id != 1
    y = linhas(crisis, "SELECT id FROM users WHERE email='y@br.org'")[0][0]
    assert linhas(crisis, "SELECT campaign_id, volunteer_id, status FROM campaign_volunteers") == [(novo_id, y, "confirmed")]
    x = linhas(crisis, "SELECT id FROM users WHERE email='x@br.org'")[0][0]
    assert linhas(crisis, "SELECT crisis_id, user_id FROM crisis_associations") == [("cemaden-1", x)]
    assert linhas(crisis, "SELECT origem, uf FROM crises WHERE id='cemaden-1'") == [("brasil", "RS")]
    assert linhas(crisis, "SELECT origem FROM crises WHERE id='usgs-1'") == [("crisis",)]
    # sem duplicar ninguém por e-mail
    assert linhas(crisis, "SELECT email, COUNT(*) FROM users GROUP BY email HAVING COUNT(*) > 1") == []


def test_fr004_simular_nao_muda_nada_e_segundo_merge_e_recusado(bancos):
    crisis, brasil = bancos
    antes = open(crisis, "rb").read()
    assert unir(crisis, brasil, simular=True)["simulado"] is True
    assert linhas(crisis, "SELECT COUNT(*) FROM users")[0][0] == 7
    assert not linhas(crisis, "SELECT name FROM sqlite_master WHERE name='brasil_merge'")
    unir(crisis, brasil)
    with pytest.raises(SystemExit, match="já recebeu"):
        unir(crisis, brasil)
    assert antes != open(crisis, "rb").read()


def test_abrigos_entram_no_merge_com_gestor_e_abrigo_remapeados(bancos):
    crisis, brasil = bancos
    b = sqlite3.connect(brasil)
    b.execute("INSERT INTO users (email, password_hash, role, name) VALUES ('gestor@br.org','h','gestor_abrigo','G')")  # id 4
    b.execute("""INSERT INTO abrigos (gestor_id, nome, lat, lon, municipio_ibge, uf, capacidade, tipo)
                 VALUES (4, 'Abrigo Fictício', -30.03, -51.22, 4314902, 'RS', 80, 'temporario')""")  # id 1
    b.execute("INSERT INTO abrigo_crises (abrigo_id, crisis_id) VALUES (1, 'cemaden-1')")
    b.commit(); b.close()
    c = sqlite3.connect(crisis)  # o Crisis já tem um abrigo com id 1: o do Brasil precisa ganhar outro id
    _preparar_crisis(c)
    c.execute("INSERT INTO abrigos (gestor_id, nome, lat, lon, capacidade, tipo) VALUES (7,'Do Crisis',-23,-46,10,'permanente')")
    c.commit(); c.close()
    rel = unir(crisis, brasil)
    assert rel["abrigos"] == 1 and rel["abrigo_crises"] == 1
    g = linhas(crisis, "SELECT id, role FROM users WHERE email='gestor@br.org'")[0]
    assert g[1] == "gestor_abrigo" and g[0] != 4
    [(aid, gid, verificado, origem)] = linhas(crisis, "SELECT id, gestor_id, verificado, origem FROM abrigos WHERE nome='Abrigo Fictício'")
    assert aid != 1 and (gid, verificado, origem) == (g[0], 0, "brasil")
    assert linhas(crisis, "SELECT abrigo_id, crisis_id FROM abrigo_crises") == [(aid, "cemaden-1")]


def test_itens_e_estoque_entram_no_merge_reaproveitando_o_item_que_o_crisis_ja_tem(bancos):
    """ADR 0007: `itens.nome_busca` é único. Item da lista base que o Crisis já tem é reaproveitado (o estoque passa
    a apontar para o id do Crisis); item novo do gestor ganha id novo e o criador remapeado."""
    crisis, brasil = bancos
    b = sqlite3.connect(brasil)
    b.execute("INSERT INTO users (email, password_hash, role, name) VALUES ('gestor@br.org','h','gestor_abrigo','G')")  # id 4
    b.execute("""INSERT INTO abrigos (gestor_id, nome, lat, lon, capacidade, tipo)
                 VALUES (4, 'Abrigo Fictício', -30.03, -51.22, 80, 'temporario')""")  # id 1
    agua_br = b.execute("SELECT id FROM itens WHERE nome_busca='agua'").fetchone()[0]
    novo_br = b.execute("""INSERT INTO itens (nome, nome_busca, grupo, unidade, criado_por)
                           VALUES ('Fraldas', 'fraldas', 'sustento', 'pacotes', 4)""").lastrowid
    b.execute("INSERT INTO abrigo_itens (abrigo_id, item_id, status, quantidade) VALUES (1, ?, 'urgente', 300)", (agua_br,))
    b.execute("INSERT INTO abrigo_itens (abrigo_id, item_id, status) VALUES (1, ?, 'precisa')", (novo_br,))
    b.commit(); b.close()
    c = sqlite3.connect(crisis)  # o Crisis já tem itens com outros ids, entre eles a mesma Água
    _preparar_crisis(c)
    assert c.execute("SELECT COUNT(*) FROM itens").fetchone()[0] == 0  # a semente não vai pelo esquema
    c.execute("INSERT INTO itens (nome, nome_busca, grupo, unidade) VALUES ('Lonas', 'lonas', 'estrutura_ativos', 'unidades')")
    c.execute("INSERT INTO itens (nome, nome_busca, grupo, unidade) VALUES ('Água', 'agua', 'sustento', 'litros')")
    c.commit(); c.close()
    total_br = linhas(brasil, "SELECT COUNT(*) FROM itens")[0][0]
    rel = unir(crisis, brasil)
    assert rel["itens"] == total_br - 1 and rel["abrigo_itens"] == 2  # a Água não foi duplicada
    assert linhas(crisis, "SELECT nome_busca, COUNT(*) FROM itens GROUP BY nome_busca HAVING COUNT(*) > 1") == []
    [(agua_cr,)] = linhas(crisis, "SELECT id FROM itens WHERE nome_busca='agua'")
    g = linhas(crisis, "SELECT id FROM users WHERE email='gestor@br.org'")[0][0]
    [(fraldas, criador)] = linhas(crisis, "SELECT id, criado_por FROM itens WHERE nome_busca='fraldas'")
    assert criador == g and fraldas != novo_br
    [(aid,)] = linhas(crisis, "SELECT id FROM abrigos WHERE nome='Abrigo Fictício'")
    assert sorted(linhas(crisis, "SELECT abrigo_id, item_id, status, quantidade FROM abrigo_itens")) == sorted(
        [(aid, agua_cr, "urgente", 300.0), (aid, fraldas, "precisa", None)])
    assert agua_cr != agua_br


def test_familias_e_abrigados_entram_no_merge_com_abrigo_e_familia_remapeados(bancos):
    crisis, brasil = bancos
    b = sqlite3.connect(brasil)
    b.execute("INSERT INTO users (email, password_hash, role, name) VALUES ('gestor@br.org','h','gestor_abrigo','G')")  # id 4
    b.execute("""INSERT INTO abrigos (gestor_id, nome, lat, lon, municipio_ibge, uf, capacidade, tipo)
                 VALUES (4, 'Abrigo Fictício', -30.03, -51.22, 4314902, 'RS', 80, 'temporario')""")  # id 1
    b.execute("INSERT INTO familias (abrigo_id) VALUES (1)")  # id 1
    b.execute("""INSERT INTO abrigados (abrigo_id, familia_id, nome, nome_mae, cpf, nome_busca, entrada_em)
                 VALUES (1, 1, 'Pessoa Fictícia Um', 'Mãe Fictícia', '12345678901', 'pessoa ficticia um', '2026-11-18T10:00:00')""")
    b.execute("""INSERT INTO abrigados (abrigo_id, nome, nome_mae, nome_busca, entrada_em)
                 VALUES (1, 'Pessoa Fictícia Dois', 'Mãe Fictícia Dois', 'pessoa ficticia dois', '2026-11-18T11:00:00')""")
    b.commit(); b.close()
    c = sqlite3.connect(crisis)  # o Crisis já tem abrigo e família com id 1: os do Brasil ganham outros ids
    _preparar_crisis(c)
    c.execute("INSERT INTO abrigos (gestor_id, nome, lat, lon, capacidade, tipo) VALUES (7,'Do Crisis',-23,-46,10,'permanente')")
    c.execute("INSERT INTO familias (abrigo_id) VALUES (1)")
    c.commit(); c.close()
    rel = unir(crisis, brasil)
    assert rel["familias"] == 1 and rel["abrigados"] == 2
    [(aid,)] = linhas(crisis, "SELECT id FROM abrigos WHERE nome='Abrigo Fictício'")
    [(fid, fab)] = linhas(crisis, "SELECT id, abrigo_id FROM familias WHERE id > 1")
    assert aid != 1 and fid != 1 and fab == aid
    assert linhas(crisis, "SELECT abrigo_id, familia_id, cpf, origem FROM abrigados ORDER BY id") == [
        (aid, fid, "12345678901", "brasil"), (aid, None, None, "brasil")]


def test_registro_de_buscas_entra_no_merge_com_usuario_remapeado(bancos):
    """ADR 0008: a auditoria da busca entre abrigos sobrevive ao merge, apontando para o usuário certo."""
    crisis, brasil = bancos
    b = sqlite3.connect(brasil)
    b.execute("INSERT INTO users (email, password_hash, role, name) VALUES ('gestor@br.org','h','gestor_abrigo','G')")  # id 4
    b.execute("""INSERT INTO buscas_abrigados_log (user_id, consulta, buscado_em, resultados)
                 VALUES (4, 'Pessoa Fictícia', '2026-11-18T13:00:00+00:00', 2)""")
    b.execute("""INSERT INTO buscas_abrigados_log (user_id, consulta, buscado_em, resultados)
                 VALUES (3, 'ninguem', '2026-11-18T13:05:00+00:00', 0)""")  # Ana: mesmo e-mail no Crisis (id 7)
    b.commit(); b.close()
    rel = unir(crisis, brasil)
    assert rel["buscas_abrigados_log"] == 2
    [(g,)] = linhas(crisis, "SELECT id FROM users WHERE email='gestor@br.org'")
    assert linhas(crisis, "SELECT user_id, consulta, buscado_em, resultados, origem FROM buscas_abrigados_log ORDER BY id") == [
        (g, "Pessoa Fictícia", "2026-11-18T13:00:00+00:00", 2, "brasil"), (7, "ninguem", "2026-11-18T13:05:00+00:00", 0, "brasil")]
    assert g != 4


def test_ident_valida_e_coloca_aspas():
    import pytest
    from middleware.brasil.merge_brasil import _ident
    assert _ident("abrigo_itens") == '"abrigo_itens"'
    assert _ident("_x1") == '"_x1"'
    for ruim in ("a;drop", 'a"b', "1abc", "", "a b", "a-b", "main.users", "a\n", None):
        with pytest.raises(ValueError):
            _ident(ruim)
