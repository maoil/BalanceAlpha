import sqlite3

conn = sqlite3.connect('data/balancealpha.db')
cursor = conn.cursor()

# 使用人工智能 ETF (159819.SZ) 作为追踪标的
cursor.execute(
    "UPDATE instruments SET tracking_index = ? WHERE symbol = ?",
    ("159819.SZ", "012734")
)
print(f"Updated {cursor.rowcount} row(s)")

cursor.execute(
    "SELECT symbol, name, tracking_index FROM instruments WHERE tracking_index IS NOT NULL AND tracking_index != ''"
)
for row in cursor.fetchall():
    print(row)

conn.commit()
conn.close()
