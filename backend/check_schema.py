import sqlite3

conn = sqlite3.connect("app.db")
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print("Tables:", tables)
for table in tables:
    print(f"\n--- {table} ---")
    cursor.execute(f"PRAGMA table_info({table})")
    for col in cursor.fetchall():
        print(col)
    cursor.execute(f"PRAGMA index_list({table})")
    for idx in cursor.fetchall():
        print("INDEX:", idx)
conn.close()