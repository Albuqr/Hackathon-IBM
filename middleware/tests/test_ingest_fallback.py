"""_coletar_eventos / _ingest_fallback com respostas gravadas (sem rede)."""
from middleware.gravacao import TIPOS_CRISE


def _por_fonte(eventos, fonte):
    return [e for e in eventos if e["source"] == fonte]


def test_coleta_usgs_e_gdacs_rss_reais(app_db, rede_gravada):
    ev = app_db._coletar_eventos()
    usgs, gdacs = _por_fonte(ev, "usgs"), _por_fonte(ev, "gdacs")
    assert len(usgs) == 4 and len(gdacs) == 5  # inclui a duplicata de cada fixture
    assert usgs[0]["crisis_type"] == "seismic" and usgs[0]["id"] == usgs[-1]["id"]
    eq = gdacs[0]
    assert eq["id"] == "gdacs-EQ1578798" and eq["severity"] == 4  # magnitude 6.5 no título
    assert (eq["lat"], eq["lon"]) != (0.0, 0.0)  # geo:Point aninhado lido corretamente
    assert [e["crisis_type"] for e in gdacs] == ["seismic", "meteorological", "drought", "wildfire", "seismic"]
    assert all(e["crisis_type"] in TIPOS_CRISE for e in ev)


def test_fallback_grava_sem_duplicar(app_db, rede_gravada):
    r = app_db._ingest_fallback()
    linhas = app_db.linhas()
    assert r["ok"] and r["triggered_by"] == "fallback" and r["errors"] == []
    assert len([i for i in linhas if i.startswith("usgs-")]) == 3
    assert len([i for i in linhas if i.startswith("gdacs-")]) == 4
    assert r["events_saved"] == len(linhas)
    assert r["events_collected"] == r["events_saved"] + 2  # as 2 duplicatas coletadas não viram linha
    assert len(app_db.avisos) == len({a["crisis_title"] for a in app_db.avisos})  # sem aviso repetido


def test_fallback_segunda_rodada_nao_grava_nada(app_db, rede_gravada):
    app_db._ingest_fallback()
    assert app_db._ingest_fallback()["events_saved"] == 0


def test_fallback_nao_sobrescreve_classificacao_existente(app_db, rede_gravada):
    from middleware.gravacao import gravar_eventos
    db = app_db.get_db()
    gravar_eventos(db, [{"id": "gdacs-EQ1578798", "title": "classificado antes", "severity": 5,
                         "urgency": "immediate", "crisis_type": "humanitarian", "source": "gdacs"}])
    db.close()
    app_db._ingest_fallback()
    linha = app_db.linhas()["gdacs-EQ1578798"]
    assert (linha["severity"], linha["urgency"], linha["crisis_type"]) == (5, "immediate", "humanitarian")
    assert linha["title"] == "classificado antes"
