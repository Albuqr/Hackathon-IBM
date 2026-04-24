"""
seed_volunteers.py
Inserts realistic test volunteers (15 per crisis) and 3 test ONG accounts.
Test users are clearly marked with names like "Voluntário Teste 01".
Run: python seed_volunteers.py
"""
import sqlite3
import hashlib
import json
import random
import math
import os

DB = os.environ.get("DB_PATH", "data/crisis.db")

SKILL_DISTRIBUTION = [
    "medical", "medical", "medical",
    "logistics", "logistics", "logistics",
    "SAR", "SAR",
    "engineering", "engineering",
    "psychology", "psychology",
    "translator",
    "general", "general",
]  # exactly 15 items

TEST_ORGS = [
    ("Cruz Vermelha Teste",        "org_cruzverm@test.com",   "Cruz Vermelha",          "humanitarian"),
    ("Médicos Sem Fronteiras Teste","org_msf@test.com",        "Médicos Sem Fronteiras", "medical"),
    ("Logística Humanitária Teste", "org_logistica@test.com",  "Log. Humanitária",       "logistics"),
]

PW_HASH = hashlib.sha256(b"test123").hexdigest()


def _rand_nearby(lat: float, lon: float, radius_km: float = 500):
    """Return a random lat/lon within radius_km of the given point."""
    # 1 degree ≈ 111 km
    deg = radius_km / 111.0
    dlat = random.uniform(-deg, deg)
    dlon = random.uniform(-deg, deg) / max(math.cos(math.radians(lat)), 0.01)
    return round(lat + dlat, 4), round(lon + dlon, 4)


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Ensure campaign_volunteers table exists
    c.executescript("""
        CREATE TABLE IF NOT EXISTS campaign_volunteers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER REFERENCES campaigns(id),
            volunteer_id INTEGER REFERENCES users(id),
            status TEXT DEFAULT 'selected',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(campaign_id, volunteer_id)
        );
    """)

    # ── Fetch all crises ──────────────────────────────────────────────
    crises = c.execute(
        "SELECT id, title, country, lat, lon FROM crises WHERE lat!=0 AND lon!=0"
    ).fetchall()
    print(f"Found {len(crises)} crises in database.")

    vol_inserted = 0
    assoc_inserted = 0

    skills_cycle = SKILL_DISTRIBUTION[:]

    for idx, crisis in enumerate(crises):
        clat, clon = crisis["lat"], crisis["lon"]
        random.shuffle(skills_cycle)

        for i, skill in enumerate(skills_cycle):
            vol_num = idx * 15 + i + 1
            name    = f"Voluntário Teste {vol_num:03d}"
            email   = f"test{vol_num:04d}@test.com"
            vlat, vlon = _rand_nearby(clat, clon, 500)

            try:
                cur = c.execute(
                    "INSERT OR IGNORE INTO users "
                    "(name, email, password_hash, role, skills, languages, "
                    "lat, lon, radius_km, available) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (name, email, PW_HASH, "volunteer",
                     json.dumps([skill]), json.dumps(["pt-BR"]),
                     vlat, vlon, 500, 1)
                )
                if cur.lastrowid:
                    vol_inserted += 1
                    user_id = cur.lastrowid
                else:
                    row = c.execute(
                        "SELECT id FROM users WHERE email=?", (email,)
                    ).fetchone()
                    user_id = row["id"] if row else None

                if user_id:
                    c.execute(
                        "INSERT OR IGNORE INTO crisis_associations "
                        "(crisis_id, user_id, role) VALUES (?,?,?)",
                        (crisis["id"], user_id, "volunteer")
                    )
                    assoc_inserted += 1
            except Exception as e:
                print(f"  Error inserting {name}: {e}")

    conn.commit()

    # ── Insert test ONG accounts ──────────────────────────────────────
    org_inserted = 0
    for org_name, email, org_display, skill in TEST_ORGS:
        try:
            c.execute(
                "INSERT OR IGNORE INTO users "
                "(name, email, password_hash, role, skills, languages, "
                "lat, lon, radius_km, org_name, available) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (org_name, email, PW_HASH, "org",
                 json.dumps([skill]), json.dumps(["pt-BR"]),
                 0, 0, 0, org_display, 1)
            )
            if c.lastrowid:
                org_inserted += 1
        except Exception as e:
            print(f"  Error inserting ONG {org_name}: {e}")

    conn.commit()
    conn.close()

    print(f"\nSeed complete:")
    print(f"  Volunteers inserted : {vol_inserted}")
    print(f"  Associations created: {assoc_inserted}")
    print(f"  ONGs inserted       : {org_inserted}")
    print(f"\nTest credentials — password: test123")
    print(f"  Volunteer: test0001@test.com")
    for _, email, _, _ in TEST_ORGS:
        print(f"  ONG:       {email}")


if __name__ == "__main__":
    main()
