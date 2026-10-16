"""FR-004: merge do brasil.db no banco do Crisis."""
import os
import runpy
import sqlite3

import pytest

from middleware.brasil import db
from middleware.brasil.config import carregar
from middleware.brasil.merge_brasil import unir

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
