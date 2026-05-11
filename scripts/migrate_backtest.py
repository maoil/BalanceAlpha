"""
数据库迁移脚本 - 添加 backtesting.py 原生回测所需的字段
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "balancealpha.db")


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 检查 backtest_runs 现有字段
    cursor.execute("PRAGMA table_info(backtest_runs)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    print("Existing backtest_runs columns:", existing_cols)

    # 检查 instruments 现有字段
    cursor.execute("PRAGMA table_info(instruments)")
    existing_inst_cols = {row[1] for row in cursor.fetchall()}
    print("Existing instruments columns:", existing_inst_cols)

    # 添加 backtest_runs 新字段
    if "instrument_id" not in existing_cols:
        cursor.execute(
            "ALTER TABLE backtest_runs ADD COLUMN instrument_id INTEGER REFERENCES instruments(id)"
        )
        print("Added instrument_id to backtest_runs")

    if "backtest_config_key" not in existing_cols:
        cursor.execute(
            "ALTER TABLE backtest_runs ADD COLUMN backtest_config_key VARCHAR(100) DEFAULT ''"
        )
        print("Added backtest_config_key to backtest_runs")

    if "warmup_start_date" not in existing_cols:
        cursor.execute(
            "ALTER TABLE backtest_runs ADD COLUMN warmup_start_date DATE"
        )
        print("Added warmup_start_date to backtest_runs")

    # 添加 instruments 新字段
    if "backtest_config_key" not in existing_inst_cols:
        cursor.execute(
            "ALTER TABLE instruments ADD COLUMN backtest_config_key VARCHAR(100) DEFAULT ''"
        )
        print("Added backtest_config_key to instruments")

    conn.commit()
    conn.close()
    print("Migration completed successfully!")


if __name__ == "__main__":
    migrate()
