"""Semeia crises fixas no brasil.db para o teste E2E do mapa (frontend/brasil/tests/e2e/mapa.spec.mjs).

Uso: BRASIL_DB_PATH=data/brasil-e2e.db python -m middleware.brasil.semear_teste
Recusa rodar sem BRASIL_DB_PATH explícito, para nunca misturar com dados reais.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

from . import db, ingestao
from .config import carregar

CRISES = [
    # AC-006.1: duas crises em Porto Alegre (4314902), severidades 2 e 4
    {"id": "teste-poa-2", "title": "Teste POA sev 2", "lat": -30.03, "lon": -51.22, "severity": 2,
     "crisis_type": "meteorological", "source": "cemaden", "municipio_ibge": 4314902},
    {"id": "teste-poa-4", "title": "Teste POA sev 4", "lat": -30.05, "lon": -51.18, "severity": 4,
     "crisis_type": "geological", "source": "cemaden", "municipio_ibge": 4314902},
    # AC-008.1: outra UF e outro tipo
    {"id": "teste-altamira", "title": "Teste Altamira queimada", "lat": -3.2, "lon": -52.2, "severity": 5,
     "crisis_type": "wildfire", "source": "inpe", "municipio_ibge": 1500602},
    {"id": "teste-caxias", "title": "Teste Caxias do Sul chuva", "lat": -29.17, "lon": -51.18, "severity": 3,
     "crisis_type": "meteorological", "source": "cemaden", "municipio_ibge": 4305108},
]


def main():
    if not os.environ.get("BRASIL_DB_PATH"):
        sys.exit("defina BRASIL_DB_PATH (ex.: data/brasil-e2e.db)")
    cfg = carregar()
    agora = datetime.now(timezone.utc)
    visto = (agora - timedelta(hours=1)).isoformat()
    por_fonte: dict[str, list] = {}
    for c in CRISES:
        por_fonte.setdefault(c["source"], []).append({**c, "visto_em": visto})
    rel = ingestao.executar(cfg, fontes={k: (lambda v=v: v) for k, v in por_fonte.items()}, agora=agora)
    conn = db.conectar(cfg)
    conn.close()
    print(f"semeado: {rel['gravadas']} crises em {cfg.db_path}")


if __name__ == "__main__":
    main()
