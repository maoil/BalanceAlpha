import sqlite3
conn = sqlite3.connect('data/balancealpha.db')
cursor = conn.cursor()
cursor.execute("SELECT id, symbol, name, instrument_type, market, backtest_config_key FROM instruments WHERE symbol LIKE '%020840%' OR name LIKE '%人工智能%'")
results = cursor.fetchall()
for r in results:
    print(r)
if not results:
    print("No matching instruments found")
    cursor.execute("SELECT id, symbol, name FROM instruments LIMIT 10")
    print("First 10 instruments:")
    for r in cursor.fetchall():
        print(r)
conn.close()
