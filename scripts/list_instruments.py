import sqlite3
conn = sqlite3.connect('data/balancealpha.db')
cursor = conn.cursor()
cursor.execute("SELECT id, symbol, name, instrument_type, market, backtest_config_key FROM instruments")
results = cursor.fetchall()
print(f"Total instruments: {len(results)}")
for r in results:
    print(r)
conn.close()
