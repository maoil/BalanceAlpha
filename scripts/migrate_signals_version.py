import sqlite3

db_path = r'data\balancealpha.db'
conn = sqlite3.connect(db_path)

try:
    conn.execute('ALTER TABLE signals ADD COLUMN batch_id TEXT DEFAULT ""')
    print("Added batch_id to signals")
except sqlite3.OperationalError as e:
    print(f"batch_id error: {e}")

try:
    conn.execute('ALTER TABLE signals ADD COLUMN batch_version INTEGER DEFAULT 1')
    print("Added batch_version to signals")
except sqlite3.OperationalError as e:
    print(f"batch_version error: {e}")

conn.commit()
conn.close()
