import sqlite3

db_path = r'C:\Users\guangxin.yang\PycharmProjects\BalanceAlpha\data\balancealpha.db'
conn = sqlite3.connect(db_path)

try:
    conn.execute('ALTER TABLE positions ADD COLUMN price_date TEXT DEFAULT ""')
    print("Added price_date")
except sqlite3.OperationalError as e:
    print(f"price_date error: {e}")

try:
    conn.execute('ALTER TABLE positions ADD COLUMN today_pnl REAL DEFAULT 0.0')
    print("Added today_pnl")
except sqlite3.OperationalError as e:
    print(f"today_pnl error: {e}")

conn.commit()

cursor = conn.execute('PRAGMA table_info(positions)')
cols = [row[1] for row in cursor.fetchall()]
print(f"Current columns: {cols}")
conn.close()
