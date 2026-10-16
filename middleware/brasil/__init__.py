"""Dash Brasil — rotas /brasil/... da API do Crisis Monitor (ADR 0001)."""


def __getattr__(nome):
    # Import tardio: os submódulos (config, malha, ingestao) podem ser usados sem subir as rotas.
    if nome == "router":
        from .rotas import router
        return router
    raise AttributeError(nome)
