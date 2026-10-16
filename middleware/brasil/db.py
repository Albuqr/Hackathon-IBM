"""Banco próprio do Dash Brasil (ADR 0002).

Mesmo esquema do Crisis (init_db.py + colunas adicionadas por middleware/main.py),
mais a coluna `origem` em cada tabela e colunas/tabelas exclusivas do Brasil.
O banco do Crisis (DB_PATH) nunca é aberto aqui.
"""
import sqlite3

from .config import Config

ESQUEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT "volunteer",
    name TEXT, phone TEXT, telegram_id INTEGER, username TEXT,
    skills TEXT DEFAULT "[]",
    languages TEXT DEFAULT "[]",
    lat REAL DEFAULT 0, lon REAL DEFAULT 0,
    radius_km REAL DEFAULT 500,
    org_name TEXT, org_cnpj TEXT,
    available BOOLEAN DEFAULT 1,
    approved BOOLEAN DEFAULT 1,
    link_code TEXT UNIQUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    origem TEXT DEFAULT 'brasil'
);
CREATE TABLE IF NOT EXISTS crises (
    id TEXT PRIMARY KEY, title TEXT,
    country TEXT, country_iso3 TEXT,
    lat REAL, lon REAL,
    severity REAL DEFAULT 0,
    urgency TEXT, crisis_type TEXT, source TEXT,
    people_affected INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    origem TEXT DEFAULT 'brasil',
    municipio_ibge INTEGER,
    uf TEXT,
    verificacao TEXT DEFAULT 'verificada' CHECK(verificacao IN ('verificada','nao_verificada','descartada')),
    link_fonte TEXT,
    municipios_afetados TEXT DEFAULT '[]',
    visto_em TEXT,
    expira_em TEXT
);
CREATE TABLE IF NOT EXISTS missions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT, description TEXT,
    lat REAL, lon REAL, location TEXT,
    skills_needed TEXT, urgency TEXT DEFAULT "Media",
    status TEXT DEFAULT "Pendente",
    org_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    crisis_id TEXT, telegram_id INTEGER, user_id INTEGER, username TEXT,
    origem TEXT DEFAULT 'brasil'
);
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crisis_id TEXT, mission_id INTEGER,
    volunteer_id INTEGER,
    score REAL, status TEXT DEFAULT "pending",
    notified_at TEXT, responded_at TEXT,
    origem TEXT DEFAULT 'brasil'
);
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id INTEGER, country_iso3 TEXT,
    origem TEXT DEFAULT 'brasil',
    PRIMARY KEY (user_id, country_iso3)
);
CREATE TABLE IF NOT EXISTS classifications_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crisis_id TEXT, severity REAL,
    urgency TEXT, crisis_type TEXT,
    confidence REAL, justification TEXT,
    needs_review BOOLEAN, trend TEXT,
    classified_at TEXT,
    origem TEXT DEFAULT 'brasil'
);
CREATE TABLE IF NOT EXISTS crisis_associations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crisis_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('volunteer','org')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    origem TEXT DEFAULT 'brasil',
    UNIQUE(crisis_id, user_id)
);
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    crisis_id TEXT DEFAULT '',
    skills_needed TEXT DEFAULT '[]',
    target_volunteers INTEGER DEFAULT 10,
    start_date TEXT DEFAULT '',
    end_date TEXT DEFAULT '',
    urgency TEXT DEFAULT 'media',
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    origem TEXT DEFAULT 'brasil'
);
CREATE TABLE IF NOT EXISTS telegram_subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    username TEXT,
    country TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    origem TEXT DEFAULT 'brasil',
    UNIQUE(telegram_id, country)
);
CREATE TABLE IF NOT EXISTS campaign_volunteers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER REFERENCES campaigns(id),
    volunteer_id INTEGER REFERENCES users(id),
    status TEXT DEFAULT 'selected',
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    origem TEXT DEFAULT 'brasil',
    UNIQUE(campaign_id, volunteer_id)
);
-- exclusivas do Dash Brasil
CREATE TABLE IF NOT EXISTS fontes_status (
    fonte TEXT PRIMARY KEY,
    ok INTEGER,
    eventos INTEGER DEFAULT 0,
    erro TEXT,
    tentativa_em TEXT,
    ultimo_ok_em TEXT
);
CREATE TABLE IF NOT EXISTS notificacoes_pendentes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canal TEXT NOT NULL,
    user_id INTEGER,
    crisis_id TEXT,
    mensagem TEXT,
    criada_em TEXT DEFAULT CURRENT_TIMESTAMP,
    origem TEXT DEFAULT 'brasil'
);
"""

_prontos: set[str] = set()


def conectar(cfg: Config) -> sqlite3.Connection:
    conn = sqlite3.connect(cfg.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if cfg.db_path not in _prontos:
        conn.executescript(ESQUEMA)
        conn.commit()
        _prontos.add(cfg.db_path)
    return conn
