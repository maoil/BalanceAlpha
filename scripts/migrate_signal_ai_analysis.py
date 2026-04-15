"""
为旧数据库初始化 signal_ai_analysis 表

用法：
    python scripts/migrate_signal_ai_analysis.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.extensions import db


def migrate() -> None:
    app = create_app()
    with app.app_context():
        db.create_all()
        print("✓ signal_ai_analysis 表已检查并初始化完成")


if __name__ == "__main__":
    migrate()
