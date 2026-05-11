import sys
sys.path.insert(0, '.')

from app import create_app
from app.services.strategy_signal_service import StrategySignalService

app = create_app()
with app.app_context():
    # 测试 012734 (易方达人工智能ETF联接C)
    result = StrategySignalService.generate_signal_for_instrument(8)
    print("Signal result:")
    for k, v in result.items():
        print(f"  {k}: {v}")
