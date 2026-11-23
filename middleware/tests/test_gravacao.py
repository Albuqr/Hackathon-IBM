"""gravar_eventos(): ponto único validado de escrita em `crises`."""
import sqlite3

import pytest

from middleware.gravacao import TIPOS_CRISE, gravar_eventos, normalizar_tipo

AGORA = "2026-01-01T00:00:00"


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE crises (id TEXT PRIMARY KEY, title TEXT, country TEXT, country_iso3 TEXT,
        lat REAL, lon REAL, severity REAL DEFAULT 0, urgency TEXT, crisis_type TEXT, source TEXT,
        people_affected INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT)""")
    yield conn
    conn.close()


def tipo_de(db, eid):
    return db.execute("SELECT crisis_type FROM crises WHERE id=?", (eid,)).fetchone()[0]


def test_evento_valido_e_inserido(db):
    r = gravar_eventos(db, [{"id": "a", "title": "T", "crisis_type": "seismic", "severity": 3}], agora=AGORA)
    assert r == {"saved": 1, "updated": 0, "ids": ["a"], "errors": []}
    assert tipo_de(db, "a") == "seismic"


def test_normaliza_crisis_type_e_aceita_type(db):
    gravar_eventos(db, [{"id": "a", "crisis_type": " DROUGHT "}, {"id": "b", "type": "Sanitary"}, {"id": "c"}])
    assert (tipo_de(db, "a"), tipo_de(db, "b"), tipo_de(db, "c")) == ("drought", "sanitary", "humanitarian")


def test_type_invalido_e_rejeitado_sem_inserir(db):
    r = gravar_eventos(db, [{"id": "x", "crisis_type": "banana"}])
    assert r["saved"] == 0 and r["ids"] == []
    assert r["errors"][0]["id"] == "x" and "banana" in r["errors"][0]["error"]
    assert db.execute("SELECT COUNT(*) FROM crises").fetchone()[0] == 0


def test_lote_misto_grava_validos_e_reporta_invalidos(db):
    r = gravar_eventos(db, [{"id": "ok1", "crisis_type": "conflict"}, {"id": "ruim", "crisis_type": "x"},
                            {"id": "ok2", "type": "wildfire"}, "nao-e-objeto", {"id": "lat", "lat": "abc"}])
    assert r["saved"] == 2 and r["ids"] == ["ok1", "ok2"]
    assert [e["id"] for e in r["errors"]] == ["ruim", None, "lat"]
    assert {x[0] for x in db.execute("SELECT id FROM crises")} == {"ok1", "ok2"}


def test_update_so_toca_severity_urgency_tipo(db):
    gravar_eventos(db, [{"id": "a", "title": "Orig", "crisis_type": "seismic", "severity": 2}], agora=AGORA)
    r = gravar_eventos(db, [{"id": "a", "title": "Novo", "crisis_type": "Wildfire", "severity": 5,
                             "urgency": "immediate"}], agora="2026-02-02T00:00:00")
    assert r["saved"] == 0 and r["updated"] == 1
    linha = db.execute("SELECT * FROM crises WHERE id='a'").fetchone()
    assert (linha["title"], linha["crisis_type"], linha["severity"], linha["urgency"]) == ("Orig", "wildfire", 5, "immediate")
    assert (linha["created_at"], linha["updated_at"]) == (AGORA, "2026-02-02T00:00:00")


def test_update_com_tipo_invalido_nao_altera_a_linha(db):
    gravar_eventos(db, [{"id": "a", "crisis_type": "seismic"}])
    r = gravar_eventos(db, [{"id": "a", "crisis_type": "banana"}])
    assert r["updated"] == 0 and len(r["errors"]) == 1
    assert tipo_de(db, "a") == "seismic"


def test_tipos_do_schema_incluem_os_usados_no_repo():
    assert {"seismic", "meteorological", "humanitarian", "conflict", "wildfire", "drought", "sanitary",
            "political", "geological", "hydrological"} == set(TIPOS_CRISE)
    assert normalizar_tipo({}) == "humanitarian"


def test_rejeicoes_vao_para_errors_com_titulo_e_para_o_log(db, caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="middleware.gravacao"):
        r = gravar_eventos(db, [{"id": "tipo", "title": "Evento X", "crisis_type": "banana"},
                                {"id": "lat", "title": "Evento Y", "lat": "abc"}, "lixo"])
    assert [(e["id"], e["title"]) for e in r["errors"]] == [("tipo", "Evento X"), ("lat", "Evento Y"), (None, None)]
    assert "banana" in r["errors"][0]["error"] and "abc" in r["errors"][1]["error"]
    avisos = [x for x in caplog.records if x.levelno == logging.WARNING]
    assert len(avisos) == 3
    texto = " ".join(x.getMessage() for x in avisos)
    assert "id=tipo" in texto and "banana" in texto and "id=lat" in texto and "abc" in texto
    assert "Evento X" not in texto  # título não vai para o log
