"""Semeia crises e convites fixos no brasil.db para o E2E (frontend/brasil/tests/e2e/app.spec.mjs),
e abrigos, pessoas e estoque fictícios dos gestores de teste `gestor` e `gestor2` (ADRs 0005–0007).

Uso: BRASIL_DB_PATH=data/brasil-e2e.db BRASIL_DEV_LOGIN=1 python -m middleware.brasil.semear_teste
Recusa rodar sem BRASIL_DB_PATH explícito, para nunca misturar com dados reais.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

from . import db, ingestao
from .config import carregar
from .merge_brasil import _sql

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
    # brasil-app AC-004.1: duas crises na mesma coordenada (Pelotas)
    {"id": "teste-pelotas-2", "title": "Teste Pelotas sev 2", "lat": -31.77, "lon": -52.34, "severity": 2,
     "crisis_type": "meteorological", "source": "cemaden", "municipio_ibge": 4314407},
    {"id": "teste-pelotas-5", "title": "Teste Pelotas sev 5", "lat": -31.77, "lon": -52.34, "severity": 5,
     "crisis_type": "hydrological", "source": "cemaden", "municipio_ibge": 4314407},
    # brasil-app AC-007.1 / AC-009.1: alerta de área centrado em SC que alcança o RS
    {"id": "teste-aviso-sc-rs", "title": "Teste aviso chuvas SC e RS", "lat": -27.59, "lon": -48.55, "severity": 3,
     "crisis_type": "meteorological", "source": "inmet", "municipio_ibge": 4205407,
     "municipios_afetados": [4205407, 4321501, 4305108]},
    # AC-026.1: crise de notícia não verificada
    {"id": "teste-noticia-recife", "title": "Teste notícia alagamento Recife", "lat": -8.05, "lon": -34.9, "severity": 3,
     "crisis_type": "meteorological", "source": "noticias", "municipio_ibge": 2611606, "verificacao": "nao_verificada",
     "link_fonte": "https://agenciabrasil.ebc.com.br/teste"},
]


def main():
    if not os.environ.get("BRASIL_DB_PATH"):
        sys.exit("defina BRASIL_DB_PATH (ex.: data/brasil-e2e.db)")
    if os.environ.get("BRASIL_DEV_LOGIN") != "1":
        sys.exit("defina BRASIL_DEV_LOGIN=1 (a semente usa os usuários de teste)")
    cfg = carregar()
    agora = datetime.now(timezone.utc)
    visto = (agora - timedelta(hours=1)).isoformat()
    por_fonte: dict[str, list] = {}
    for c in CRISES:
        por_fonte.setdefault(c["source"], []).append({**c, "visto_em": visto})
    rel = ingestao.executar(cfg, fontes={k: (lambda v=v: v) for k, v in por_fonte.items()}, agora=agora)
    voluntarios(cfg)
    convites(cfg, agora)
    resumo = abrigos_teste(cfg, agora)
    print(f"semeado: {rel['gravadas']} crises em {cfg.db_path}")
    # só contagens: nunca nomes de pessoas abrigadas (ADR 0006)
    print("abrigos: {abrigos}, pessoas: {pessoas} ({presentes} presentes), famílias: {familias}, "
          "itens de estoque: {estoque}".format(**resumo))


VOLUNTARIOS = [  # campanha guiada: matching com habilidades em comum perto das crises do RS
    ("Bruno Matos", ["resgate", "motorista", "logística"], -30.0, -51.2),
    ("Elisa Moura", ["resgate", "primeiros socorros"], -29.9, -51.1),
    ("Carla Nunes", ["logística", "abrigo", "cozinha"], -30.1, -51.3),
    ("Rafael Lima", ["abrigo", "logística"], -29.7, -51.1),
    ("Júlia Campos", ["primeiros socorros", "enfermagem"], -31.7, -52.3),
    ("Paula Fontes", ["comunicação", "psicologia"], -29.2, -51.2),
]


def voluntarios(cfg):
    import json
    conn = db.conectar(cfg)
    try:
        conn.execute("DELETE FROM campaign_volunteers WHERE volunteer_id IN "
                     "(SELECT id FROM users WHERE email LIKE 'semente-%@teste.brasil')")
        conn.execute("DELETE FROM users WHERE email LIKE 'semente-%@teste.brasil'")
        for i, (nome, habs, lat, lon) in enumerate(VOLUNTARIOS):
            conn.execute("INSERT INTO users (email, password_hash, role, name, skills, lat, lon, radius_km) VALUES (?,?,?,?,?,?,?,?)",
                         (f"semente-{i}@teste.brasil", "-", "volunteer", nome, json.dumps(habs, ensure_ascii=False), lat, lon, 500))
        conn.commit()
    finally:
        conn.close()


def convites(cfg, agora):
    """brasil-app AC-016.1: a ONG de teste convida a voluntária de teste para 2 campanhas (convites pendentes)."""
    from . import rotas  # cria os usuários de teste como o dev-login faria
    ong, vol = rotas.dev_usuario("ong")["id"], rotas.dev_usuario("voluntario")["id"]
    conn = db.conectar(cfg)
    try:
        conn.execute("DELETE FROM campaign_volunteers")
        conn.execute("DELETE FROM campaigns")
        conn.execute("DELETE FROM crisis_associations")
        conn.execute("UPDATE crises SET verificacao='nao_verificada' WHERE id='teste-noticia-recife'")
        for titulo, crise, habs in (("Teste campanha POA", "teste-poa-4", '["resgate", "primeiros socorros"]'),
                                    ("Teste campanha Caxias", "teste-caxias", '["abrigo", "logística"]')):
            cid = conn.execute("""INSERT INTO campaigns (org_id, title, crisis_id, skills_needed, target_volunteers, status, created_at)
                                  VALUES (?,?,?,?,5,'active',?)""", (ong, titulo, crise, habs, agora.isoformat())).lastrowid
            conn.execute("INSERT INTO campaign_volunteers (campaign_id, volunteer_id, status, added_at) VALUES (?,?,'selected',?)",
                          (cid, vol, agora.isoformat()))
        conn.commit()
    finally:
        conn.close()


# ── abrigos de teste (ADRs 0005–0007) ─────────────────────────────────
# Tudo fictício: nomes inventados ("Exemplo", "Teste", "Fictício"), nenhum CPF.
# Pessoa: (nome, nome da mãe, necessidades, dias desde a entrada, dias desde a saída ou None).
# Uma chegada com 2+ pessoas vira uma família, como na API.
ABRIGOS_TESTE = [
    {"gestor": "gestor", "nome": "Ginásio da Escola Estadual Fictícia", "endereco": "Rua de Teste, 100 – Porto Alegre",
     "lat": -30.0346, "lon": -51.2177, "capacidade": 60, "tipo": "permanente", "sensivel": False,
     "crises": ["teste-poa-4"],
     "chegadas": [
         [("Carlos Exemplo Ramos", "Odete Exemplo Ramos", [], 3, None),
          ("Beatriz Exemplo Ramos", "Lurdes Fictícia Prado", ["gestante"], 3, None),
          ("Lucas Exemplo Ramos", "Beatriz Exemplo Ramos", [], 3, None)],  # criança, sem CPF
         [("Ivone Teste Moraes", "Cecília Teste Moraes", ["idoso", "saude"], 2, None)],
         [("Rui Fictício Dantas", "Alda Fictícia Dantas", ["deficiencia"], 2, None)],
         [("Pedro Fictício Lima", "Neusa Fictícia Lima", [], 4, 1)],  # já saiu
     ],
     "estoque": [("agua", "urgente", 500), ("colchoes", "sobrando", 20), ("equipe de saude", "precisa", 2),
                 ("cesta basica", "ok", 30)]},
    {"gestor": "gestor2", "nome": "Ginásio Municipal de Teste", "endereco": "Avenida Fictícia, 200 – Canoas",
     "lat": -29.9177, "lon": -51.1836, "capacidade": 40, "tipo": "temporario", "sensivel": False, "crises": [],
     "chegadas": [
         [("Marta Exemplo Nunes", "Iara Exemplo Nunes", [], 1, None),
          ("Davi Exemplo Nunes", "Marta Exemplo Nunes", [], 1, None)],
         [("Sílvio Teste Barros", "Rosa Teste Barros", ["idoso"], 1, None)],
     ],
     "estoque": [("agua", "ok", 200), ("cobertores", "urgente", 50), ("ambulancia", "precisa", 1)]},
    {"gestor": "gestor2", "nome": "Casa de Acolhimento de Teste", "endereco": "Endereço reservado (teste)",
     "lat": -29.92, "lon": -51.17, "capacidade": 12, "tipo": "permanente", "sensivel": True, "crises": [],
     "chegadas": [[("Joana Fictícia Reis", "Sara Fictícia Reis", ["saude"], 5, None)]],
     "estoque": [("roupas", "precisa", 30)]},
]


def abrigos_teste(cfg, agora) -> dict:
    """Recria os abrigos de teste de `gestor` e `gestor2` (todos os abrigos desses dois, só deles), não verificados.
    Idempotente: apaga antes estoque, pessoas, famílias, vínculos e abrigos desses gestores. Devolve só contagens."""
    import json
    from . import rotas  # cria os usuários de teste como o dev-login faria
    from .abrigados import nome_busca
    from .abrigos import local
    gestores = {p: rotas.dev_usuario(p)["id"] for p in ("gestor", "gestor2")}
    conn = db.conectar(cfg)
    try:
        ids = tuple(gestores.values())
        for tabela in ("abrigo_itens", "abrigados", "familias", "abrigo_crises"):
            conn.execute(_sql("DELETE FROM {t} WHERE abrigo_id IN (SELECT id FROM abrigos WHERE gestor_id IN (?,?))", t=tabela), ids)
        conn.execute("DELETE FROM abrigos WHERE gestor_id IN (?,?)", ids)
        resumo = {"abrigos": 0, "pessoas": 0, "presentes": 0, "familias": 0, "estoque": 0}
        for a in ABRIGOS_TESTE:
            lugar = local(a["lat"], a["lon"])
            aid = conn.execute(
                """INSERT INTO abrigos (gestor_id, nome, endereco, lat, lon, municipio_ibge, uf, capacidade, tipo, ativo,
                   sensivel, verificado, criado_em) VALUES (?,?,?,?,?,?,?,?,?,1,?,0,?)""",
                (gestores[a["gestor"]], a["nome"], a["endereco"], a["lat"], a["lon"], lugar["municipio_ibge"], lugar["uf"],
                 a["capacidade"], a["tipo"], int(a["sensivel"]), (agora - timedelta(days=6)).isoformat())).lastrowid
            resumo["abrigos"] += 1
            conn.executemany("INSERT INTO abrigo_crises (abrigo_id, crisis_id) VALUES (?,?)",
                             [(aid, c) for c in a["crises"] if conn.execute("SELECT 1 FROM crises WHERE id=?", (c,)).fetchone()])
            for chegada in a["chegadas"]:
                familia = None
                if len(chegada) > 1:
                    familia = conn.execute("INSERT INTO familias (abrigo_id) VALUES (?)", (aid,)).lastrowid
                    resumo["familias"] += 1
                for nome, mae, nec, dias, saiu in chegada:
                    saida = (agora - timedelta(days=saiu)).isoformat(timespec="seconds") if saiu is not None else None
                    conn.execute(
                        """INSERT INTO abrigados (abrigo_id, familia_id, nome, nome_mae, cpf, nome_busca, entrada_em, saida_em,
                           necessidades) VALUES (?,?,?,?,NULL,?,?,?,?)""",
                        (aid, familia, nome, mae, nome_busca(nome), (agora - timedelta(days=dias)).isoformat(timespec="seconds"),
                         saida, json.dumps(nec)))
                    resumo["pessoas"] += 1
                    resumo["presentes"] += saida is None
            for item, status, qtd in a["estoque"]:  # itens da lista base (db.ESQUEMA), pelo nome_busca
                iid = conn.execute("SELECT id FROM itens WHERE nome_busca=?", (item,)).fetchone()["id"]
                conn.execute("INSERT INTO abrigo_itens (abrigo_id, item_id, status, quantidade, atualizado_em) VALUES (?,?,?,?,?)",
                             (aid, iid, status, qtd, agora.isoformat()))
                resumo["estoque"] += 1
        conn.commit()
        return resumo
    finally:
        conn.close()


if __name__ == "__main__":
    main()
