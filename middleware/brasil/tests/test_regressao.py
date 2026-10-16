"""NFR-004 / AC-002.1: a API do Crisis continua com as rotas atuais e ganha só /brasil."""


# AC-002.1
def test_ac_002_1_api_do_crisis_mantem_rotas_e_inclui_brasil(ambiente):
    import middleware.main as main
    rotas = set(main.app.openapi()["paths"])
    assert {"/events", "/campaigns", "/ingest", "/chat", "/predictions"} <= rotas
    assert "/brasil/saude" in rotas
    novas = {r for r in rotas if r.startswith("/brasil")}
    assert all(r.startswith("/brasil/") for r in novas)
