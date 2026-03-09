import sqlite3

def get_connection():
    conn = sqlite3.connect("reviews.db", check_same_thread=False)
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        repo_name TEXT,
        commit_id TEXT,
        score REAL,
        summary TEXT,
        report_json TEXT
    )
    """)

    conn.commit()
    conn.close()
    