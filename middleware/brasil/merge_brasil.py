"""Une o brasil.db ao banco do Crisis (FR-004, ADR 0002).

    python -m middleware.brasil.merge_brasil --crisis data/crisis.db --brasil data/brasil.db [--simular]

- Tudo numa transação: ou entra tudo, ou nada muda.
- Usuários com o mesmo e-mail viram uma conta só (a do Crisis); os outros ganham IDs novos.
- IDs inteiros (campanhas, missões, convites…) são renumerados; IDs de crises (texto, únicos por fonte) são mantidos.
- Colunas e tabelas exclusivas do Brasil são adicionadas ao banco do Crisis (só adição, nada é removido).
- Recusa rodar duas vezes no mesmo banco (tabela `brasil_merge`), a menos que se passe --forcar.
"""
import argparse
import sqlite3
import sys
from datetime import datetime, timezone

from .db import ESQUEMA

# tabela → {coluna: tabela cujo ID ela referencia}
REFERENCIAS = {
    "campaigns": {"org_id": "users"},
    "campaign_volunteers": {"campaign_id": "campaigns", "volunteer_id": "users"},
    "crisis_associations": {"user_id": "users"},
    "missions": {"user_id": "users", "org_id": "users"},
    "matches": {"volunteer_id": "users", "mission_id": "missions"},
    "subscriptions": {"user_id": "users"},
    "notificacoes_pendentes": {"user_id": "users"},
}
ORDEM = ["campaigns", "campaign_volunteers", "crisis_associations", "missions", "matches",
         "subscriptions", "classifications_log", "telegram_subscribers", "notificacoes_pendentes"]


def _colunas(conn, banco: str, tabela: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA {banco}.table_info({tabela})")]


def _preparar_crisis(conn):
    """Cria no banco do Crisis o que falta do esquema Brasil (tabelas e colunas), sem tocar no que existe."""
    temp = sqlite3.connect(":memory:")
    temp.executescript(ESQUEMA)
    for (tabela,) in temp.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        ddl = temp.execute("SELECT sql FROM sqlite_master WHERE name=?", (tabela,)).fetchone()[0]
        if not _colunas(conn, "main", tabela):
            conn.execute(ddl)
            continue
        existentes = set(_colunas(conn, "main", tabela))
        for col in temp.execute(f"PRAGMA table_info({tabela})"):
            nome, tipo, padrao = col[1], col[2], col[4]
            if nome == "origem":
                padrao = "'crisis'"  # linhas que já existem (e as futuras do Crisis) são do Crisis
            if nome not in existentes:
                # SQLite não aceita UNIQUE/CHECK em ADD COLUMN: vai só o tipo e o padrão
                conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}" + (f" DEFAULT {padrao}" if padrao is not None else ""))
    temp.close()


def unir(crisis_path: str, brasil_path: str, simular: bool = False, forcar: bool = False) -> dict:
    conn = sqlite3.connect(crisis_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    rel = {"usuarios_unificados": 0, "usuarios_novos": 0, "crises": 0}
    try:
        conn.execute("BEGIN")
        if not _colunas(conn, "main", "users"):
            raise SystemExit(f"{crisis_path} não parece o banco do Crisis (sem tabela users)")
        conn.execute("CREATE TABLE IF NOT EXISTS brasil_merge (feito_em TEXT, origem TEXT, relatorio TEXT)")
        if conn.execute("SELECT 1 FROM brasil_merge").fetchone() and not forcar:
            raise SystemExit("este banco já recebeu um merge do Brasil; use --forcar para repetir")
        _preparar_crisis(conn)
        conn.execute("ATTACH DATABASE ? AS br", (brasil_path,))

        mapa: dict[str, dict[int, int]] = {"users": {}}
        # usuários: unifica por e-mail
        cols = [c for c in _colunas(conn, "br", "users") if c != "id"]
        for u in conn.execute("SELECT * FROM br.users").fetchall():
            existe = conn.execute("SELECT id FROM main.users WHERE lower(email)=lower(?)", (u["email"],)).fetchone()
            if existe:
                mapa["users"][u["id"]] = existe["id"]
                rel["usuarios_unificados"] += 1
                continue
            valores = [u[c] for c in cols]
            if "link_code" in cols and u["link_code"] and conn.execute(
                    "SELECT 1 FROM main.users WHERE link_code=?", (u["link_code"],)).fetchone():
                valores[cols.index("link_code")] = None  # código repetido: o Crisis gera outro na subida
            cur = conn.execute(f"INSERT INTO main.users ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", valores)
            mapa["users"][u["id"]] = cur.lastrowid
            rel["usuarios_novos"] += 1

        # crises: IDs de texto mantidos; a versão do Brasil prevalece
        ccols = _colunas(conn, "br", "crises")
        rel["crises"] = conn.execute(
            f"INSERT OR REPLACE INTO main.crises ({', '.join(ccols)}) SELECT {', '.join(ccols)} FROM br.crises").rowcount

        for tabela in ORDEM:
            tcols = _colunas(conn, "br", tabela)
            if not tcols:
                continue
            tem_id = "id" in tcols
            outras = [c for c in tcols if c != "id"]
            mapa[tabela] = {}
            n = 0
            for linha in conn.execute(f"SELECT * FROM br.{tabela}").fetchall():
                valores = []
                for c in outras:
                    v = linha[c]
                    alvo = REFERENCIAS.get(tabela, {}).get(c)
                    if alvo and v is not None:
                        v = mapa.get(alvo, {}).get(v, v)
                    valores.append(v)
                cur = conn.execute(
                    f"INSERT OR IGNORE INTO main.{tabela} ({', '.join(outras)}) VALUES ({', '.join('?' * len(outras))})", valores)
                if tem_id and cur.rowcount:
                    mapa[tabela][linha["id"]] = cur.lastrowid
                n += cur.rowcount
            rel[tabela] = n

        fcols = _colunas(conn, "br", "fontes_status")
        conn.execute(f"INSERT OR REPLACE INTO main.fontes_status ({', '.join(fcols)}) SELECT {', '.join(fcols)} FROM br.fontes_status")
        conn.execute("INSERT INTO brasil_merge VALUES (?,?,?)",
                     (datetime.now(timezone.utc).isoformat(), brasil_path, str(rel)))
        conn.execute("ROLLBACK" if simular else "COMMIT")
        rel["simulado"] = simular
        return rel
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Une o brasil.db ao banco do Crisis.")
    ap.add_argument("--crisis", required=True, help="banco do Crisis (DB_PATH)")
    ap.add_argument("--brasil", required=True, help="banco do Dash Brasil (BRASIL_DB_PATH)")
    ap.add_argument("--simular", action="store_true", help="faz tudo e desfaz no fim; só mostra o relatório")
    ap.add_argument("--forcar", action="store_true", help="permite repetir o merge no mesmo banco")
    a = ap.parse_args(argv)
    print(unir(a.crisis, a.brasil, simular=a.simular, forcar=a.forcar))


if __name__ == "__main__":
    sys.exit(main())
