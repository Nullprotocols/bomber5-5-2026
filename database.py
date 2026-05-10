# database.py – Advanced Telegram Bomber Bot (100% WORKING)
import sqlite3
import os
from typing import List, Optional, Dict

DB_FILE = "bot_data.db"

def get_connection():
    """Return a database connection with row factory."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create all tables if they don't exist and enable WAL mode."""
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
            phone TEXT PRIMARY KEY
        )
    ''')
    c.execute("PRAGMA journal_mode=WAL;")
    conn.commit()
    conn.close()

def add_user(user_id: int, username: Optional[str], first_name: Optional[str]):
    """Add a new user if not already present."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name)
        VALUES (?, ?, ?)
    ''', (user_id, username, first_name))
    conn.commit()
    conn.close()

def is_admin(user_id: int) -> bool:
    """Check if user is admin (owner or role=admin)."""
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
    """Check if user is the bot owner."""
    owner_id = os.getenv("OWNER_ID")
    return owner_id and str(user_id) == owner_id

def set_admin_role(user_id: int, make_admin: bool):
    """Promote or demote user to/from admin."""
    role = 'admin' if make_admin else 'user'
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET role = ? WHERE user_id = ?', (role, user_id))
    conn.commit()
    conn.close()

def ban_user(user_id: int) -> bool:
    """Ban a user. Returns True if user existed."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET banned = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0

def unban_user(user_id: int) -> bool:
    """Unban a user. Returns True if user existed and was banned."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET banned = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0

def delete_user(user_id: int) -> bool:
    """Delete user from database. Returns True if user existed."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0

def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Get user record by ID."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_user_target(user_id: int, target: Optional[str]):
    """Store the target phone number for a user (used by admin lookup)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET target_number = ? WHERE user_id = ?', (target, user_id))
    conn.commit()
    conn.close()

def get_user_target(user_id: int) -> Optional[str]:
    """Retrieve the stored target phone number for a user."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT target_number FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row['target_number'] if row else None

def update_user_phone(user_id: int, phone: str):
    """Store user's own phone number (protected) for self‑bombing prevention."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET user_phone = ? WHERE user_id = ?', (phone, user_id))
    conn.commit()
    conn.close()

def get_user_phone(user_id: int) -> Optional[str]:
    """Retrieve user's own phone number."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT user_phone FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row['user_phone'] if row else None

def get_all_users_paginated(page: int, per_page: int = 10) -> List[Dict]:
    """Return a page of users sorted by user_id."""
    offset = page * per_page
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT user_id, username, first_name, role, joined_at, banned
        FROM users
        ORDER BY user_id
        LIMIT ? OFFSET ?
    ''', (per_page, offset))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_recent_users_paginated(page: int, per_page: int = 10, days: int = 7) -> List[Dict]:
    """Return a page of users who joined in the last N days, ordered by join date descending."""
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
    return [dict(row) for row in rows]

def get_all_user_ids() -> List[int]:
    """Return list of all user IDs."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT user_id FROM users')
    rows = c.fetchall()
    conn.close()
    return [row['user_id'] for row in rows]

def get_user_count() -> int:
    """Return total number of users."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    count = c.fetchone()[0]
    conn.close()
    return count

# ---------- Protected Numbers (Global Blacklist) ----------
def add_protected_number(phone: str):
    """Add a number to the protected list."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO protected_numbers (phone) VALUES (?)', (phone,))
    conn.commit()
    conn.close()

def remove_protected_number(phone: str) -> bool:
    """Remove a number from the protected list. Returns True if it existed."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM protected_numbers WHERE phone = ?', (phone,))
    conn.commit()
    affected = c.rowcount
    conn.close()
    return affected > 0

def is_protected_number(phone: str) -> bool:
    """Check if a number is protected (cannot be bombed)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT 1 FROM protected_numbers WHERE phone = ?', (phone,))
    row = c.fetchone()
    conn.close()
    return row is not None

def get_all_protected_numbers() -> List[str]:
    """Return all protected phone numbers."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT phone FROM protected_numbers ORDER BY phone')
    rows = c.fetchall()
    conn.close()
    return [row['phone'] for row in rows]
