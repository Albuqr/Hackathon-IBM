import sqlite3
import hashlib
import os

os.makedirs('data', exist_ok=True)
conn = sqlite3.connect('data/crisis.db')
c = conn.cursor()

c.executescript('''
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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS crises (
    id TEXT PRIMARY KEY, title TEXT,
    country TEXT, country_iso3 TEXT,
    lat REAL, lon REAL,
    severity REAL DEFAULT 0,
    urgency TEXT, crisis_type TEXT, source TEXT,
    people_affected INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS missions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT, description TEXT,
    lat REAL, lon REAL, location TEXT,
    skills_needed TEXT, urgency TEXT DEFAULT "Media",
    status TEXT DEFAULT "Pendente",
    org_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crisis_id TEXT, mission_id INTEGER,
    volunteer_id INTEGER,
    score REAL, status TEXT DEFAULT "pending",
    notified_at TEXT, responded_at TEXT
);
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id INTEGER, country_iso3 TEXT,
    PRIMARY KEY (user_id, country_iso3)
);
CREATE TABLE IF NOT EXISTS classifications_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crisis_id TEXT, severity REAL,
    urgency TEXT, crisis_type TEXT,
    confidence REAL, justification TEXT,
    needs_review BOOLEAN, trend TEXT,
    classified_at TEXT
);
CREATE TABLE IF NOT EXISTS crisis_associations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    crisis_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('volunteer','org')),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS telegram_subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    username TEXT,
    country TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(telegram_id, country)
);
CREATE TABLE IF NOT EXISTS campaign_volunteers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER REFERENCES campaigns(id),
    volunteer_id INTEGER REFERENCES users(id),
    status TEXT DEFAULT 'selected',
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(campaign_id, volunteer_id)
);
''')

# Add columns if they don't exist yet (SQLite doesn't support IF NOT EXISTS for ALTER)
for _sql in [
    'ALTER TABLE users ADD COLUMN username TEXT',
    'ALTER TABLE users ADD COLUMN link_code TEXT UNIQUE',
    'ALTER TABLE missions ADD COLUMN crisis_id TEXT',
    'ALTER TABLE missions ADD COLUMN telegram_id INTEGER',
    'ALTER TABLE missions ADD COLUMN user_id INTEGER',
    'ALTER TABLE missions ADD COLUMN username TEXT',
]:
    try:
        c.execute(_sql)
    except Exception:
        pass

admin_hash = hashlib.sha256(b'admin123').hexdigest()
c.execute(
    'INSERT OR IGNORE INTO users (email, password_hash, role, name) VALUES (?, ?, ?, ?)',
    ('admin@hktn26.com', admin_hash, 'admin', 'Administrador')
)

conn.commit()
conn.close()
print('Banco inicializado com sucesso!')