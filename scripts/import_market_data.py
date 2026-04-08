"""
行情数据导入脚本

用法：
    python scripts/import_market_data.py <产品代码> <CSV文件路径>

CSV 格式要求（表头）：
    trade_date, open, high, low, close, volume, nav, acc_nav

示例：
    python scripts/import_market_data.py 159941 data/imports/159941.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.extensions import db
from app.models.instrument import Instrument
from app.services.market_data_service import MarketDataService


def main():
    if len(sys.argv) < 3:
        print("用法: python scripts/import_market_data.py <产品代码> <CSV文件路径>")
        print("示例: python scripts/import_market_data.py 159941 data/imports/159941.csv")
        sys.exit(1)

    symbol = sys.argv[1]
    csv_path = sys.argv[2]

    if not Path(csv_path).exists():
        print(f"❌ 文件不存在: {csv_path}")
        sys.exit(1)

    app = create_app()
    with app.app_context():
        instrument = Instrument.query.filter_by(symbol=symbol).first()
        if not instrument:
            print(f"❌ 产品 {symbol} 不存在，请先在系统中注册")
            sys.exit(1)

        print(f"正在导入 {symbol} ({instrument.name}) 的行情数据...")
        result = MarketDataService.import_csv(csv_path, instrument.id)

        print(f"\n导入完成:")
        print(f"  导入: {result['imported']} 条")
        print(f"  跳过: {result['skipped']} 条 (已存在)")
        if result["errors"]:
            print(f"  错误: {len(result['errors'])} 条")
            for err in result["errors"][:5]:
                print(f"    - {err}")


if __name__ == "__main__":
    main()
