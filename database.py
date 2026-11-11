import sqlite3
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "findmyitem.db"

def get_connection():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def initialize_database():
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            report_type TEXT NOT NULL CHECK(report_type IN ('Lost','Found')),
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            incident_date TEXT NOT NULL,
            image_path TEXT,
            private_clue TEXT,
            status TEXT NOT NULL DEFAULT 'Open',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lost_report_id INTEGER NOT NULL,
            found_report_id INTEGER NOT NULL,
            claimant_id INTEGER NOT NULL,
            proof_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            reviewer_note TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(lost_report_id, found_report_id),
            FOREIGN KEY(lost_report_id) REFERENCES reports(id),
            FOREIGN KEY(found_report_id) REFERENCES reports(id),
            FOREIGN KEY(claimant_id) REFERENCES users(id)
        );
        """)
        conn.commit()

def create_user(name, email, password_hash, role="user"):
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
            (name.strip(), email.strip().lower(), password_hash, role, now)
        )
        conn.commit()
        return cur.lastrowid

def get_user_by_email(email):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()

def get_user_by_id(user_id):
    with get_connection() as conn:
        return conn.execute("SELECT id,name,email,role FROM users WHERE id=?", (user_id,)).fetchone()

def create_report(data):
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO reports(
                user_id, report_type, item_name, category, description,
                location, latitude, longitude, incident_date, image_path,
                private_clue, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data["user_id"], data["report_type"], data["item_name"],
            data["category"], data["description"], data["location"],
            data.get("latitude"), data.get("longitude"), data["incident_date"],
            data.get("image_path"), data.get("private_clue"), now
        ))
        conn.commit()
        return cur.lastrowid

def get_reports(report_type=None, exclude_user_id=None):
    query = """
        SELECT r.*, u.name AS reporter_name
        FROM reports r JOIN users u ON u.id = r.user_id
        WHERE r.status = 'Open'
    """
    params = []
    if report_type:
        query += " AND r.report_type = ?"
        params.append(report_type)
    if exclude_user_id is not None:
        query += " AND r.user_id != ?"
        params.append(exclude_user_id)
    query += " ORDER BY r.created_at DESC"
    with get_connection() as conn:
        return conn.execute(query, params).fetchall()

def get_user_reports(user_id):
    with get_connection() as conn:
        return conn.execute("""
            SELECT * FROM reports WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,)).fetchall()

def get_report(report_id):
    with get_connection() as conn:
        return conn.execute("""
            SELECT r.*, u.name AS reporter_name
            FROM reports r JOIN users u ON u.id=r.user_id
            WHERE r.id=?
        """, (report_id,)).fetchone()

def create_claim(lost_report_id, found_report_id, claimant_id, proof_text):
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO claims(
                lost_report_id, found_report_id, claimant_id, proof_text,
                status, created_at, updated_at
            ) VALUES(?,?,?,?, 'Pending', ?, ?)
        """, (lost_report_id, found_report_id, claimant_id, proof_text, now, now))
        conn.commit()
        return cur.lastrowid

def get_claims_for_user(user_id):
    with get_connection() as conn:
        return conn.execute("""
            SELECT c.*, l.item_name AS lost_item, f.item_name AS found_item,
                   f.user_id AS finder_id, u.name AS claimant_name
            FROM claims c
            JOIN reports l ON l.id=c.lost_report_id
            JOIN reports f ON f.id=c.found_report_id
            JOIN users u ON u.id=c.claimant_id
            WHERE c.claimant_id=? OR f.user_id=?
            ORDER BY c.created_at DESC
        """, (user_id, user_id)).fetchall()

def update_claim_status(claim_id, status, reviewer_note=""):
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_connection() as conn:
        conn.execute("""
            UPDATE claims SET status=?, reviewer_note=?, updated_at=?
            WHERE id=?
        """, (status, reviewer_note, now, claim_id))
        conn.commit()

def get_all_claims():
    with get_connection() as conn:
        return conn.execute("""
            SELECT c.*, l.item_name AS lost_item, f.item_name AS found_item,
                   f.user_id AS finder_id, u.name AS claimant_name
            FROM claims c
            JOIN reports l ON l.id=c.lost_report_id
            JOIN reports f ON f.id=c.found_report_id
            JOIN users u ON u.id=c.claimant_id
            ORDER BY c.created_at DESC
        """).fetchall()

def get_admin_stats():
    with get_connection() as conn:
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        lost = conn.execute("SELECT COUNT(*) FROM reports WHERE report_type='Lost'").fetchone()[0]
        found = conn.execute("SELECT COUNT(*) FROM reports WHERE report_type='Found'").fetchone()[0]
        claims = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM claims WHERE status='Pending'").fetchone()[0]
    return {"users": users, "lost": lost, "found": found, "claims": claims, "pending": pending}

def admin_reports():
    with get_connection() as conn:
        return conn.execute("""
            SELECT r.id, r.report_type, r.item_name, r.category, r.location,
                   r.status, r.created_at, u.email
            FROM reports r JOIN users u ON u.id=r.user_id
            ORDER BY r.created_at DESC
        """).fetchall()
