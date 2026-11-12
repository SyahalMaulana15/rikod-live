import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'app.db')
MEMBERS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'members.json')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()
    
    # Recordings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE,
            member_name TEXT,
            member_username TEXT,
            title TEXT,
            slug TEXT,
            file_path TEXT,
            file_name TEXT,
            file_size INTEGER DEFAULT 0,
            duration INTEGER DEFAULT 0,
            status TEXT DEFAULT 'recording',
            engine TEXT DEFAULT 'native',
            cloud_status TEXT DEFAULT 'none',
            cloud_url TEXT,
            cloud_provider TEXT,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    ''')
    
    # Members watchlist table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            nickname TEXT,
            username TEXT UNIQUE,
            generation TEXT,
            avatar_url TEXT,
            auto_record INTEGER DEFAULT 0,
            is_jkt48 INTEGER DEFAULT 1
        )
    ''')
    
    # Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Default settings
    default_settings = {
        "storage_path": os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recordings'),
        "recording_engine": "native", # "native", "ytdlp", "ffmpeg"
        "auto_record_all_jkt48": "0", # "1" or "0"
        "poll_interval": "20", # seconds
        "cloud_provider": "none", # "none", "gdrive", "rclone", "s3"
        "cloud_auto_upload": "0",
        "cloud_delete_after_upload": "0",
        "gdrive_folder_id": "",
        "gdrive_service_account_json": "",
        "rclone_remote_name": "gdrive:JKT48_Live",
        "s3_endpoint_url": "",
        "s3_bucket_name": "",
        "s3_access_key": "",
        "s3_secret_key": "",
        "s3_region": "auto",
        "discord_webhook_url": "",
        "telegram_bot_token": "",
        "telegram_chat_id": ""
    }
    
    for k, v in default_settings.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
    # Seed members from members.json if empty
    cursor.execute("SELECT COUNT(*) FROM members")
    count = cursor.fetchone()[0]
    if count == 0 and os.path.exists(MEMBERS_JSON_PATH):
        try:
            with open(MEMBERS_JSON_PATH, 'r', encoding='utf-8') as f:
                members_data = json.load(f)
                for m in members_data:
                    cursor.execute('''
                        INSERT OR IGNORE INTO members (name, nickname, username, generation, avatar_url, auto_record, is_jkt48)
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                    ''', (
                        m.get('name', ''),
                        m.get('nickname', ''),
                        m.get('username', '').lower(),
                        m.get('generation', ''),
                        m.get('avatar_url', ''),
                        1 if m.get('auto_record', False) else 0
                    ))
        except Exception as e:
            print(f"[DB] Error seeding members: {e}")
            
    conn.commit()
    conn.close()

def get_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    return {row['key']: row['value'] for row in rows}

def update_setting(key, value):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def update_settings_bulk(settings_dict):
    conn = get_db()
    cursor = conn.cursor()
    for k, v in settings_dict.items():
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
    conn.commit()
    conn.close()

def get_all_members():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM members ORDER BY auto_record DESC, name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_member_auto_record(member_id, auto_record):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE members SET auto_record = ? WHERE id = ?", (1 if auto_record else 0, member_id))
    conn.commit()
    conn.close()

def add_member(name, nickname, username, generation="", avatar_url="", auto_record=False):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO members (name, nickname, username, generation, avatar_url, auto_record, is_jkt48)
        VALUES (?, ?, ?, ?, ?, ?, 1)
    ''', (name, nickname, username.lower().strip(), generation, avatar_url, 1 if auto_record else 0))
    conn.commit()
    conn.close()

def delete_member(member_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM members WHERE id = ?", (member_id,))
    conn.commit()
    conn.close()

def create_recording_entry(task_id, member_name, member_username, title, slug, file_path, file_name, engine):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO recordings (
            task_id, member_name, member_username, title, slug, file_path, file_name, engine, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'recording', CURRENT_TIMESTAMP)
    ''', (task_id, member_name, member_username, title, slug, file_path, file_name, engine))
    conn.commit()
    rec_id = cursor.lastrowid
    conn.close()
    return rec_id

def update_recording_status(task_id, status, file_size=0, duration=0, error_message=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE recordings 
        SET status = ?, 
            file_size = CASE WHEN ? > 0 THEN ? ELSE file_size END,
            duration = CASE WHEN ? > 0 THEN ? ELSE duration END,
            error_message = ?,
            completed_at = CASE WHEN ? IN ('completed', 'failed', 'stopped') THEN CURRENT_TIMESTAMP ELSE completed_at END
        WHERE task_id = ?
    ''', (status, file_size, file_size, duration, duration, error_message, status, task_id))
    conn.commit()
    conn.close()

def update_recording_cloud_status(task_id, cloud_status, cloud_url=None, cloud_provider=None, error_message=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE recordings 
        SET cloud_status = ?,
            cloud_url = COALESCE(?, cloud_url),
            cloud_provider = COALESCE(?, cloud_provider),
            error_message = COALESCE(?, error_message)
        WHERE task_id = ?
    ''', (cloud_status, cloud_url, cloud_provider, error_message, task_id))
    conn.commit()
    conn.close()

def get_recordings(limit=100, offset=0):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM recordings ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_recording_by_id(rec_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM recordings WHERE id = ?", (rec_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_recording_by_task_id(task_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM recordings WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_recording_entry(rec_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT file_path FROM recordings WHERE id = ?", (rec_id,))
    row = cursor.fetchone()
    cursor.execute("DELETE FROM recordings WHERE id = ?", (rec_id,))
    conn.commit()
    conn.close()
    return row['file_path'] if row else None
