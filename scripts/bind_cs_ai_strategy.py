"""
Bind CS人工智能 strategy to 易方达人工智能ETF联接C (012734)
"""
import sqlite3

conn = sqlite3.connect('data/balancealpha.db')
cursor = conn.cursor()

cursor.execute(
    "UPDATE instruments SET backtest_config_key = ? WHERE symbol = ?",
    ("cs_ai_momentum", "012734")
)

rows_affected = cursor.rowcount
print(f"Updated {rows_affected} row(s)")

cursor.execute(
    "SELECT id, symbol, name, backtest_config_key FROM instruments WHERE symbol = ?",
    ("012734",)
)
result = cursor.fetchone()
if result:
    print(f"Verified: id={result[0]}, symbol={result[1]}, name={result[2]}, config_key={result[3]}")
else:
    print("Product not found!")

conn.commit()
conn.close()
print("Done!")
