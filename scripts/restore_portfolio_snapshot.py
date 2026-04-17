from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from app import create_app
from app.extensions import db
from app.models.account import Account
from app.models.instrument import Instrument
from app.models.market_data import MarketData
from app.models.position import Position
from app.models.strategy_assignment import StrategyAssignment
from app.models.strategy_template import StrategyTemplate, get_default_assignment_range
from app.models.trade import Trade
from app.models.system_log import SystemLog
from app.services.instrument_service import InstrumentService
from app.services.position_service import PositionService


@dataclass(frozen=True)
class HoldingSnapshot:
    account_code: str
    symbol: str
    name: str
    snapshot_date: date
    quantity: float
    avg_cost: float
    market_price: float
    today_pnl: float
    unrealized_pnl: float
    market_value: float
    instrument_type: str
    trade_mode: str
    default_strategy_template: str
    is_dca_eligible: bool


HOLDINGS = [
    HoldingSnapshot(
        account_code="core",
        symbol="513110",
        name="纳指100ETF",
        snapshot_date=date(2026, 4, 17),
        quantity=1000.00,
        avg_cost=2.0810,
        market_price=2.1270,
        today_pnl=-16.00,
        unrealized_pnl=46.00,
        market_value=2127.00,
        instrument_type="etf",
        trade_mode="exchange_traded",
        default_strategy_template="core_index_template",
        is_dca_eligible=True,
    ),
    HoldingSnapshot(
        account_code="core",
        symbol="161125",
        name="标普500LOF",
        snapshot_date=date(2026, 4, 17),
        quantity=500.00,
        avg_cost=2.7530,
        market_price=2.9450,
        today_pnl=-3.50,
        unrealized_pnl=96.00,
        market_value=1472.50,
        instrument_type="lof",
        trade_mode="exchange_traded",
        default_strategy_template="core_index_template",
        is_dca_eligible=True,
    ),
    HoldingSnapshot(
        account_code="core",
        symbol="017731",
        name="嘉实全球产业升级股票(QDII)C",
        snapshot_date=date(2026, 4, 15),
        quantity=900.00,
        avg_cost=2.7118,
        market_price=3.1157,
        today_pnl=4.21,
        unrealized_pnl=363.51,
        market_value=2804.13,
        instrument_type="fund",
        trade_mode="eod_nav",
        default_strategy_template="core_active_fund_template",
        is_dca_eligible=True,
    ),
    HoldingSnapshot(
        account_code="core",
        symbol="012922",
        name="易方达全球成长精选混合(DQII)C",
        snapshot_date=date(2026, 4, 15),
        quantity=778.71,
        avg_cost=2.8202,
        market_price=3.1943,
        today_pnl=2.98,
        unrealized_pnl=291.32,
        market_value=2487.43,
        instrument_type="fund",
        trade_mode="eod_nav",
        default_strategy_template="core_active_fund_template",
        is_dca_eligible=True,
    ),
    HoldingSnapshot(
        account_code="core",
        symbol="014662",
        name="天弘上海金ETF联接C",
        snapshot_date=date(2026, 4, 16),
        quantity=1447.33,
        avg_cost=2.4104,
        market_price=2.3613,
        today_pnl=-20.51,
        unrealized_pnl=-71.06,
        market_value=3417.58,
        instrument_type="fund",
        trade_mode="eod_nav",
        default_strategy_template="gold_hedge_template",
        is_dca_eligible=False,
    ),
    HoldingSnapshot(
        account_code="core",
        symbol="008164",
        name="南方标普中国A股大盘红利低波50联接C",
        snapshot_date=date(2026, 4, 16),
        quantity=1400.00,
        avg_cost=1.0465,
        market_price=1.0465,
        today_pnl=0.00,
        unrealized_pnl=0.00,
        market_value=1465.10,
        instrument_type="fund",
        trade_mode="eod_nav",
        default_strategy_template="dividend_low_vol_template",
        is_dca_eligible=True,
    ),
    HoldingSnapshot(
        account_code="tactical",
        symbol="020485",
        name="中欧中证全指软件开发指数C",
        snapshot_date=date(2026, 4, 16),
        quantity=1662.40,
        avg_cost=1.2031,
        market_price=1.1842,
        today_pnl=-10.24,
        unrealized_pnl=-31.39,
        market_value=1968.61,
        instrument_type="fund",
        trade_mode="eod_nav",
        default_strategy_template="tactical_theme_template",
        is_dca_eligible=False,
    ),
    HoldingSnapshot(
        account_code="tactical",
        symbol="012734",
        name="易方达人工智能ETF联接C",
        snapshot_date=date(2026, 4, 16),
        quantity=1189.97,
        avg_cost=1.7776,
        market_price=1.9261,
        today_pnl=42.17,
        unrealized_pnl=176.76,
        market_value=2292.00,
        instrument_type="fund",
        trade_mode="eod_nav",
        default_strategy_template="tactical_theme_template",
        is_dca_eligible=False,
    ),
    HoldingSnapshot(
        account_code="tactical",
        symbol="019455",
        name="华泰柏瑞中证韩交所中韩半导体ETF联接(DQII)C",
        snapshot_date=date(2026, 4, 16),
        quantity=396.62,
        avg_cost=2.3448,
        market_price=2.7529,
        today_pnl=0.00,
        unrealized_pnl=161.87,
        market_value=1091.86,
        instrument_type="fund",
        trade_mode="eod_nav",
        default_strategy_template="tactical_theme_template",
        is_dca_eligible=False,
    ),
]


def ensure_instrument(snapshot: HoldingSnapshot) -> Instrument:
    instrument = Instrument.query.filter_by(symbol=snapshot.symbol).first()
    payload = {
        "symbol": snapshot.symbol,
        "name": snapshot.name,
        "instrument_type": snapshot.instrument_type,
        "trade_mode": snapshot.trade_mode,
        "default_account_type": snapshot.account_code,
        "default_strategy_template": snapshot.default_strategy_template,
        "is_dca_eligible": snapshot.is_dca_eligible,
        "status": "active",
    }

    if instrument is None:
        return InstrumentService.create(payload)

    instrument.name = snapshot.name
    instrument.instrument_type = snapshot.instrument_type
    instrument.trade_mode = snapshot.trade_mode
    instrument.default_account_type = snapshot.account_code
    instrument.default_strategy_template = snapshot.default_strategy_template
    instrument.is_dca_eligible = snapshot.is_dca_eligible
    instrument.status = "active"
    db.session.commit()

    InstrumentService._auto_create_assignment(instrument, payload)
    return instrument


def ensure_market_data(instrument: Instrument, snapshot: HoldingSnapshot) -> None:
    market_data = MarketData.query.filter_by(
        instrument_id=instrument.id,
        trade_date=snapshot.snapshot_date,
    ).first()

    if market_data is None:
        market_data = MarketData(
            instrument_id=instrument.id,
            trade_date=snapshot.snapshot_date,
        )
        db.session.add(market_data)

    if snapshot.trade_mode == "exchange_traded":
        market_data.open = snapshot.market_price
        market_data.high = snapshot.market_price
        market_data.low = snapshot.market_price
        market_data.close = snapshot.market_price
        market_data.nav = None
        market_data.acc_nav = None
    else:
        market_data.open = None
        market_data.high = None
        market_data.low = None
        market_data.close = None
        market_data.nav = snapshot.market_price
        market_data.acc_nav = snapshot.market_price


def ensure_assignment(account_id: int, instrument: Instrument, snapshot: HoldingSnapshot) -> None:
    template = StrategyTemplate.query.filter_by(
        template_code=snapshot.default_strategy_template
    ).first()
    if template is None:
        raise RuntimeError(f"Missing strategy template: {snapshot.default_strategy_template}")

    default_lower, default_upper = get_default_assignment_range(
        snapshot.default_strategy_template,
        symbol=snapshot.symbol,
        name=snapshot.name,
    )
    assignment = StrategyAssignment.query.filter_by(
        account_id=account_id,
        instrument_id=instrument.id,
    ).first()

    if assignment is None:
        assignment = StrategyAssignment(
            account_id=account_id,
            instrument_id=instrument.id,
        )
        db.session.add(assignment)

    assignment.template_id = template.id
    assignment.target_weight_lower = default_lower
    assignment.target_weight_upper = default_upper
    assignment.allow_dca = snapshot.is_dca_eligible
    assignment.allow_rebalance = True
    assignment.status = "active"


def ensure_position(account_id: int, instrument_id: int, snapshot: HoldingSnapshot) -> Position:
    cost_value = snapshot.quantity * snapshot.avg_cost
    unrealized_pnl_pct = (snapshot.unrealized_pnl / cost_value) if cost_value else 0.0

    position = PositionService.create_manual(
        account_id=account_id,
        instrument_id=instrument_id,
        quantity=snapshot.quantity,
        avg_cost=snapshot.avg_cost,
        market_price=snapshot.market_price,
        market_value=snapshot.market_value,
        unrealized_pnl=snapshot.unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
    )
    position.price_date = snapshot.snapshot_date.isoformat()
    position.today_pnl = snapshot.today_pnl
    position.opened_at = snapshot.snapshot_date
    position.position_status = "open"
    db.session.commit()
    return position


def ensure_restore_trade(account_id: int, instrument_id: int, snapshot: HoldingSnapshot) -> Trade:
    trade = Trade.query.filter_by(
        account_id=account_id,
        instrument_id=instrument_id,
        trade_date=snapshot.snapshot_date,
        trade_type="manual_adjust",
        reason_code="snapshot_restore",
    ).first()

    amount = round(snapshot.quantity * snapshot.avg_cost, 2)
    notes = "根据持仓快照恢复的初始化记录，非真实逐笔成交流水。"

    if trade is None:
        trade = Trade(
            account_id=account_id,
            instrument_id=instrument_id,
            trade_date=snapshot.snapshot_date,
            trade_type="manual_adjust",
            side="buy",
        )
        db.session.add(trade)

    trade.quantity = snapshot.quantity
    trade.price = snapshot.avg_cost
    trade.amount = amount
    trade.fee = 0.0
    trade.reason_code = "snapshot_restore"
    trade.notes = notes
    db.session.commit()
    return trade


def create_restore_log(restored_symbols: list[str]) -> None:
    log = SystemLog(
        log_type="data_import",
        level="info",
        module="scripts.restore_portfolio_snapshot",
        message="根据 2026-04-17 持仓快照恢复产品、策略绑定、持仓与最新行情。",
        context_json=json.dumps(
            {
                "source": "manual_snapshot",
                "restored_symbols": restored_symbols,
                "restored_trade_history": False,
            },
            ensure_ascii=False,
        ),
    )
    db.session.add(log)
    db.session.commit()


def main() -> None:
    app = create_app()
    with app.app_context():
        account_map = {
            account.account_code: account
            for account in Account.query.filter(Account.account_code.in_(["core", "tactical"])).all()
        }
        missing_accounts = {"core", "tactical"} - set(account_map.keys())
        if missing_accounts:
            raise RuntimeError(f"Missing accounts: {sorted(missing_accounts)}")

        restored_symbols: list[str] = []
        for snapshot in HOLDINGS:
            instrument = ensure_instrument(snapshot)
            ensure_assignment(account_map[snapshot.account_code].id, instrument, snapshot)
            ensure_market_data(instrument, snapshot)
            ensure_position(account_map[snapshot.account_code].id, instrument.id, snapshot)
            ensure_restore_trade(account_map[snapshot.account_code].id, instrument.id, snapshot)
            restored_symbols.append(snapshot.symbol)

        PositionService.recalculate_weights()
        db.session.commit()
        create_restore_log(restored_symbols)

        assignment_count = StrategyAssignment.query.count()
        position_count = Position.query.count()
        market_data_count = MarketData.query.count()
        trade_count = Trade.query.count()
        print(
            json.dumps(
                {
                    "restored_symbols": restored_symbols,
                    "strategy_assignments": assignment_count,
                    "positions": position_count,
                    "market_data": market_data_count,
                    "trades": trade_count,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
