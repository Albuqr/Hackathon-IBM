"""Ponto único de gravação de eventos na tabela `crises` (T4).

Normaliza e valida o tipo da crise antes de gravar. Mantém a semântica que /save_event(s) já tinham:
id existente -> UPDATE de severity, urgency, crisis_type e updated_at; id novo -> INSERT.
"""
from datetime import datetime

# União dos tipos realmente usados no código: README (crises.crisis_type), prompt do classify_crisis
# ("political") e módulo de abrigos/Brasil ("geological", "hydrological").
TIPOS_CRISE = frozenset({
    "seismic", "meteorological", "humanitarian", "conflict", "wildfire", "drought", "sanitary",
    "political", "geological", "hydrological",
})
TIPO_PADRAO = "humanitarian"


def normalizar_tipo(evento: dict) -> str:
    """crisis_type (ou, na falta, type), sem espaços e em minúsculas; ausente vira o padrão."""
    bruto = evento.get("crisis_type") or evento.get("type")
    if bruto is None or str(bruto).strip() == "":
        return TIPO_PADRAO
    return str(bruto).strip().lower()


def gravar_eventos(db, eventos, agora: str = None) -> dict:
    """Grava uma lista de eventos em `db` (conexão sqlite3) e faz commit.

    Devolve {"saved": inserções, "updated": atualizações, "ids": [...], "errors": [{"id", "error"}]}.
    Um evento inválido (tipo fora de TIPOS_CRISE, dado malformado) vira erro e não derruba o lote.
    """
    agora = agora or datetime.utcnow().isoformat()
    saved = updated = 0
    ids, errors = [], []
    for evento in eventos:
        if not isinstance(evento, dict):
            errors.append({"id": None, "error": "evento deve ser um objeto"})
            continue
        eid = evento.get("id") or f"api-{agora}-{saved}"
        try:
            tipo = normalizar_tipo(evento)
            if tipo not in TIPOS_CRISE:
                raise ValueError(f"crisis_type inválido: {tipo!r} (válidos: {', '.join(sorted(TIPOS_CRISE))})")
            existe = db.execute("SELECT id FROM crises WHERE id=?", (eid,)).fetchone()
            if existe:
                db.execute(
                    "UPDATE crises SET severity=?, urgency=?, crisis_type=?, updated_at=? WHERE id=?",
                    (evento.get("severity", 1), evento.get("urgency", "monitoring"), tipo, agora, eid),
                )
                updated += 1
            else:
                db.execute("""
                    INSERT INTO crises
                    (id, title, country, country_iso3, lat, lon,
                     severity, urgency, crisis_type, source,
                     people_affected, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    eid,
                    evento.get("title", ""),
                    evento.get("country", ""),
                    evento.get("country_iso3", "UNK"),
                    float(evento.get("lat", 0)),
                    float(evento.get("lon", 0)),
                    evento.get("severity", 1),
                    evento.get("urgency", "monitoring"),
                    tipo,
                    evento.get("source", "api"),
                    int(evento.get("people_affected", 0)),
                    agora, agora,
                ))
                saved += 1
            ids.append(eid)
        except Exception as e:
            errors.append({"id": eid, "error": str(e)})
    db.commit()
    return {"saved": saved, "updated": updated, "ids": ids, "errors": errors}
