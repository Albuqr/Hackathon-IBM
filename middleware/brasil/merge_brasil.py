"""Une o brasil.db ao banco do Crisis (FR-004, ADR 0002).

    python -m middleware.brasil.merge_brasil --crisis data/crisis.db --brasil data/brasil.db [--simular]

- Tudo numa transação: ou entra tudo, ou nada muda.
- Usuários com o mesmo e-mail viram uma conta só (a do Crisis); os outros ganham IDs novos.
- IDs inteiros (campanhas, missões, convites…) são renumerados; IDs de crises (texto, únicos por fonte) são mantidos.
- Colunas e tabelas exclusivas do Brasil são adicionadas ao banco do Crisis (só adição, nada é removido).
- Recusa rodar duas vezes no mesmo banco (tabela `brasil_merge`), a menos que se passe --forcar.
"""
import argparse
import re
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
    "abrigos": {"gestor_id": "users"},
    "abrigo_crises": {"abrigo_id": "abrigos"},  # sem id próprio: a chave (abrigo_id, crisis_id) é remapeada
    "itens": {"criado_por": "users"},
    "abrigo_itens": {"abrigo_id": "abrigos", "item_id": "itens"},
    # abrigados (ADR 0006)
    "familias": {"abrigo_id": "abrigos"},
    "abrigados": {"abrigo_id": "abrigos", "familia_id": "familias"},
    "buscas_abrigados_log": {"user_id": "users"},  # auditoria da busca (ADR 0008)
}
# tabela com id próprio e uma coluna UNIQUE: a linha que já existe no Crisis é reaproveitada (ADR 0007)
CHAVE_NATURAL = {"itens": "nome_busca"}
ORDEM = ["campaigns", "campaign_volunteers", "crisis_associations", "missions", "matches",
         "subscriptions", "classifications_log", "telegram_subscribers", "notificacoes_pendentes",
         "abrigos", "abrigo_crises", "itens", "abrigo_itens", "familias", "abrigados",
         "buscas_abrigados_log"]


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _ident(nome: str) -> str:
    """Valida um nome de tabela/coluna/banco e o devolve entre aspas duplas, pronto para entrar no SQL.
    Os nomes vêm do próprio esquema (PRAGMA), nunca do usuário; a validação garante isso mesmo assim."""
    if not isinstance(nome, str) or not _IDENT.fullmatch(nome):
        raise ValueError(f"nome inválido para SQL: {nome!r}")
    return f'"{nome}"'


_TRECHO = re.compile(r"""[A-Za-z0-9_ .()'"\[\]{}-]*""")


def _lista(nomes) -> str:
    return ", ".join(_ident(n) for n in nomes)


def _sql(modelo: str, **nomes) -> str:
    """Preenche `{chave}` do modelo com nomes validados por _ident (um nome) ou _lista (lista de nomes).
    É o único ponto onde nomes de tabela/coluna entram num SQL; valores continuam sempre em parâmetros `?`."""
    def trocar(m):
        chave, v = m.group(1), nomes[m.group(1)]
        if chave == "marcas":  # número de parâmetros `?`
            return ", ".join("?" * int(v))
        if chave in ("tipo", "padrao"):  # trechos do ESQUEMA do projeto (ex.: INTEGER, 'crisis', 0)
            if not _TRECHO.fullmatch(v):
                raise ValueError(f"trecho de esquema inválido para SQL: {v!r}")
            return v
        return _lista(v) if isinstance(v, (list, tuple)) else _ident(v)
    return re.sub(r"\{(\w+)\}", trocar, modelo)


def _colunas(conn, banco: str, tabela: str) -> list[str]:
    return [r[1] for r in conn.execute(_sql("PRAGMA {b}.table_info({t})", b=banco, t=tabela))]


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
        for col in temp.execute(_sql("PRAGMA table_info({t})", t=tabela)):
            nome, tipo, padrao = col[1], col[2], col[4]
            if nome == "origem":
                padrao = "'crisis'"  # linhas que já existem (e as futuras do Crisis) são do Crisis
            if nome not in existentes:
                # SQLite não aceita UNIQUE/CHECK em ADD COLUMN: vai só o tipo e o padrão
                # tipo e padrão vêm do ESQUEMA do próprio projeto (constantes), só os nomes são interpolados
                if padrao is None:
                    conn.execute(_sql("ALTER TABLE {t} ADD COLUMN {c} {tipo}", t=tabela, c=nome, tipo=tipo))
                else:
                    conn.execute(_sql("ALTER TABLE {t} ADD COLUMN {c} {tipo} DEFAULT {padrao}",
                                      t=tabela, c=nome, tipo=tipo, padrao=str(padrao)))
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
            cur = conn.execute(_sql("INSERT INTO main.users ({c}) VALUES ({marcas})", c=cols, marcas=len(cols)), valores)
            mapa["users"][u["id"]] = cur.lastrowid
            rel["usuarios_novos"] += 1

        # crises: IDs de texto mantidos; a versão do Brasil prevalece
        ccols = _colunas(conn, "br", "crises")
        rel["crises"] = conn.execute(
            _sql("INSERT OR REPLACE INTO main.crises ({c}) SELECT {c} FROM br.crises", c=ccols)).rowcount

        for tabela in ORDEM:
            tcols = _colunas(conn, "br", tabela)
            if not tcols:
                continue
            tem_id = "id" in tcols
            outras = [c for c in tcols if c != "id"]
            mapa[tabela] = {}
            n = 0
            ler = _sql("SELECT * FROM br.{t}", t=tabela)
            inserir = _sql("INSERT OR IGNORE INTO main.{t} ({c}) VALUES ({marcas})", t=tabela, c=outras, marcas=len(outras))
            for linha in conn.execute(ler).fetchall():
                valores = []
                for c in outras:
                    v = linha[c]
                    alvo = REFERENCIAS.get(tabela, {}).get(c)
                    if alvo and v is not None:
                        v = mapa.get(alvo, {}).get(v, v)
                    valores.append(v)
                cur = conn.execute(inserir, valores)
                if tem_id and cur.rowcount:
                    mapa[tabela][linha["id"]] = cur.lastrowid
                elif tem_id and tabela in CHAVE_NATURAL:  # ignorada pelo UNIQUE: aponta para a do Crisis
                    col = CHAVE_NATURAL[tabela]
                    achar = _sql("SELECT id FROM main.{t} WHERE {c}=?", t=tabela, c=col)
                    existe = conn.execute(achar, (linha[col],)).fetchone()
                    if existe:
                        mapa[tabela][linha["id"]] = existe["id"]
                n += cur.rowcount
            rel[tabela] = n

        fcols = _colunas(conn, "br", "fontes_status")
        conn.execute(_sql("INSERT OR REPLACE INTO main.fontes_status ({c}) SELECT {c} FROM br.fontes_status", c=fcols))
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
