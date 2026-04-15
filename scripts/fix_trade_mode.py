# -*- coding: utf-8 -*-
方达纳斯达克ETF联接C     -> eod_nav（联接基金，场外申赎）
"""
import sqlite3

FIXES = [
    ("012922", "eod_nav", "fund"),
    ("012734", "eod_nav", "fund"),
]

conn = sqlite3.connect("data/balancealpha.db")
cur = conn.cursor()

for symbol, trade_mode, inst_type in FIXES:
    cur.execute(
        "SELECT id, name, trade_mode, instrument_type FROM instruments WHERE symbol = ?",
        (symbol,),
    )
    row = cur.fetchone()
    if row:
        print(f"  BEFORE [{symbol}] id={row[0]} name={row[1]} trade_mode={row[2]} type={row[3]}")
        cur.execute(
            "UPDATE instruments SET trade_mode = ?, instrument_type = ? WHERE symbol = ?",
            (trade_mode, inst_type, symbol),
        )
        print(f"  AFTER  [{symbol}] trade_mode -> {trade_mode}, instrument_type -> {inst_type}")
    else:
        print(f"  SKIP   [{symbol}] not found")

conn.commit()
conn.close()
print("\nDone.")
