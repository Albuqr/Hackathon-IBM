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
-- gestão de abrigos (ADR 0005): o abrigo nasce não verificado e já funciona
CREATE TABLE IF NOT EXISTS abrigos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gestor_id INTEGER NOT NULL REFERENCES users(id),
    nome TEXT NOT NULL,
    endereco TEXT DEFAULT '',
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    municipio_ibge INTEGER,
    uf TEXT,
    capacidade INTEGER NOT NULL CHECK(capacidade > 0),
    tipo TEXT NOT NULL CHECK(tipo IN ('permanente','temporario')),
    ativo INTEGER DEFAULT 1,
    sensivel INTEGER DEFAULT 0,
    verificado INTEGER DEFAULT 0,
    verificado_em TEXT,
    criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
    origem TEXT DEFAULT 'brasil'
);
CREATE TABLE IF NOT EXISTS abrigo_crises (
    abrigo_id INTEGER NOT NULL REFERENCES abrigos(id),
    crisis_id TEXT NOT NULL,
    PRIMARY KEY (abrigo_id, crisis_id)
);
-- estoque e necessidades dos abrigos (ADR 0007): lista de itens compartilhada, que cresce
CREATE TABLE IF NOT EXISTS itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    nome_busca TEXT NOT NULL UNIQUE,
    grupo TEXT NOT NULL CHECK(grupo IN ('sustento','profissionais','energia_mobilidade','estrutura_ativos')),
    unidade TEXT NOT NULL DEFAULT 'unidades',
    so_necessidade INTEGER NOT NULL DEFAULT 0 CHECK(so_necessidade IN (0,1)),
    criado_por INTEGER REFERENCES users(id),
    criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
    origem TEXT DEFAULT 'brasil'
);
CREATE TABLE IF NOT EXISTS abrigo_itens (
    abrigo_id INTEGER NOT NULL REFERENCES abrigos(id),
    item_id INTEGER NOT NULL REFERENCES itens(id),
    status TEXT NOT NULL CHECK(status IN ('urgente','precisa','ok','sobrando')),
    quantidade REAL CHECK(quantidade IS NULL OR quantidade >= 0),
    atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP,
    origem TEXT DEFAULT 'brasil',
    PRIMARY KEY (abrigo_id, item_id)
);
-- lista base (nome_busca = estoque.normalizar(nome)); INSERT OR IGNORE: roda em toda subida sem duplicar
INSERT OR IGNORE INTO itens (nome, nome_busca, grupo, unidade, so_necessidade) VALUES
    ('Alimentos', 'alimentos', 'sustento', 'kg', 0),
    ('Cesta básica', 'cesta basica', 'sustento', 'cestas', 0),
    ('Água', 'agua', 'sustento', 'litros', 0),
    ('Equipe de saúde', 'equipe de saude', 'profissionais', 'pessoas', 1),
    ('Bombeiros', 'bombeiros', 'profissionais', 'pessoas', 1),
    ('Polícia', 'policia', 'profissionais', 'pessoas', 1),
    ('Gasolina', 'gasolina', 'energia_mobilidade', 'litros', 0),
    ('Etanol', 'etanol', 'energia_mobilidade', 'litros', 0),
    ('Diesel', 'diesel', 'energia_mobilidade', 'litros', 0),
    ('AVGAS', 'avgas', 'energia_mobilidade', 'litros', 0),
    ('Carro', 'carro', 'energia_mobilidade', 'veículos', 1),
    ('Caminhão', 'caminhao', 'energia_mobilidade', 'veículos', 1),
    ('Ambulância', 'ambulancia', 'energia_mobilidade', 'veículos', 1),
    ('Colchões', 'colchoes', 'estrutura_ativos', 'unidades', 0),
    ('Cobertores', 'cobertores', 'estrutura_ativos', 'unidades', 0),
    ('Roupas', 'roupas', 'estrutura_ativos', 'peças', 0),
    ('Ferramentas', 'ferramentas', 'estrutura_ativos', 'unidades', 0);
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
