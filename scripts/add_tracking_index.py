"""
Add tracking_index column to instruments table
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "balancealpha.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if column exists
    cursor.execute("PRAGMA table_info(instruments)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "tracking_index" not in columns:
        cursor.execute("ALTER TABLE instruments ADD COLUMN tracking_index TEXT DEFAULT ''")
        print("Added tracking_index column to instruments table")
    else:
        print("tracking_index column already exists")
    
    # Set tracking_index for 易方达人工智能ETF联接C (012734)
    # CS人工智能指数代码: 000977.SH
    cursor.execute(
        "UPDATE instruments SET tracking_index = ? WHERE symbol = ?",
        ("000977.SH", "012734")
    )
    print(f"Updated {cursor.rowcount} row(s) with tracking_index")
    
    conn.commit()
    conn.close()
    print("Done!")

if __name__ == "__main__":
    migrate()
