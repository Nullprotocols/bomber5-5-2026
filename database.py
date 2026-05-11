import sqlite3
import os
from typing import List, Optional, Dict

DB_FILE = "bot_data.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            role TEXT DEFAULT 'user',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            banned INTEGER DEFAULT 0,
            target_number TEXT,
            user_phone TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS protected_numbers (
            number TEXT PRIMARY KEY,
            added_by INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_users_banned ON users(banned)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)')
    conn.commit()
    conn.close()

def add_user(user_id: int, username: Optional[str], first_name: Optional[str]):
    conn = get_connection()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
              (user_id, username, first_name))
    conn.commit()
    conn.close()

def is_admin(user_id: int) -> bool:
    owner_id = os.getenv("OWNER_ID")
    if owner_id and str(user_id) == owner_id:
        return True
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT role FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row and row['role'] == 'admin'

def is_owner(user_id: int) -> bool:
    owner_id = os.getenv("OWNER_ID")
    return owner_id and str(user_id) == owner_id

def set_admin_role(user_id: int, make_admin: bool):
    role = 'admin' if make_admin else 'user'
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET role = ? WHERE user_id = ?', (role, user_id))
    conn.commit()
    conn.close()

def ban_user(user_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET banned = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0

def unban_user(user_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET banned = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0

def delete_user(user_id: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0

def get_user_by_id(user_id: int) -> Optional[Dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_user_target(user_id: int, target: Optional[str]):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET target_number = ? WHERE user_id = ?', (target, user_id))
    conn.commit()
    conn.close()

def get_user_target(user_id: int) -> Optional[str]:
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT target_number FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row['target_number'] if row else None

def update_user_phone(user_id: int, phone: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET user_phone = ? WHERE user_id = ?', (phone, user_id))
    conn.commit()
    conn.close()

def get_user_phone(user_id: int) -> Optional[str]:
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT user_phone FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row['user_phone'] if row else None

def get_all_users_paginated(page: int, per_page: int = 10) -> List[Dict]:
    offset = page * per_page
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT user_id, username, first_name, role, joined_at, banned FROM users ORDER BY user_id LIMIT ? OFFSET ?',
              (per_page, offset))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_recent_users_paginated(page: int, per_page: int = 10, days: int = 7) -> List[Dict]:
    offset = page * per_page
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT user_id, username, first_name, role, joined_at, banned
        FROM users
        WHERE joined_at >= datetime('now', ?)
        ORDER BY joined_at DESC
        LIMIT ? OFFSET ?
    ''', (f'-{days} days', per_page, offset))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_user_ids() -> List[int]:
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT user_id FROM users')
    rows = c.fetchall()
    conn.close()
    return [r['user_id'] for r in rows]

def get_user_count() -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    count = c.fetchone()[0]
    conn.close()
    return count

def add_protected_number(number: str, added_by: int) -> bool:
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO protected_numbers (number, added_by) VALUES (?, ?)', (number, added_by))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def remove_protected_number(number: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM protected_numbers WHERE number = ?', (number,))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def is_protected(number: str) -> bool:
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT 1 FROM protected_numbers WHERE number = ?', (number,))
    row = c.fetchone()
    conn.close()
    return row is not None

def get_all_protected_numbers() -> List[str]:
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT number FROM protected_numbers ORDER BY added_at DESC')
    rows = c.fetchall()
    conn.close()
    return [r['number'] for r in rows]
