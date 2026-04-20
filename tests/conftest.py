from datetime import date
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import create_app
from app.extensions import db
from app.models.account import Account
from app.models.instrument import Instrument
from app.models.market_data import MarketData
from app.models.position import Position
from app.models.strategy_assignment import StrategyAssignment
from app.models.strategy_template import StrategyTemplate


@pytest.fixture
def app(monkeypatch):
    db_dir = Path("data/test_dbs")
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / f"test_{uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    app = create_app("default")

    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def factories(app):
    def create_account(
        account_code: str = "core",
        account_name: str = "核心账户",
        account_type: str = "core",
    ) -> Account:
        account = Account(
            account_code=account_code,
            account_name=account_name,
            account_type=account_type,
            status="active",
        )
        db.session.add(account)
        db.session.commit()
        return account

    def create_template(
        template_code: str,
        template_name: str,
        account_type: str,
        config: dict,
        version: str = "1.0",
    ) -> StrategyTemplate:
        template = StrategyTemplate(
            template_code=template_code,
            template_name=template_name,
            account_type=account_type,
            description="test",
            config_json=json_dumps(config),
            version=version,
            status="active",
        )
        db.session.add(template)
        db.session.commit()
        return template

    def create_instrument(
        symbol: str,
        name: str,
        instrument_type: str = "etf",
        trade_mode: str = "exchange_traded",
        default_account_type: str = "core",
    ) -> Instrument:
        instrument = Instrument(
            symbol=symbol,
            name=name,
            instrument_type=instrument_type,
            trade_mode=trade_mode,
            default_account_type=default_account_type,
            status="active",
        )
        db.session.add(instrument)
        db.session.commit()
        return instrument

    def create_assignment(
        account_id: int,
        instrument_id: int,
        template_id: int,
        lower: float,
        upper: float,
        allow_dca: bool = True,
    ) -> StrategyAssignment:
        assignment = StrategyAssignment(
            account_id=account_id,
            instrument_id=instrument_id,
            template_id=template_id,
            target_weight_lower=lower,
            target_weight_upper=upper,
            allow_dca=allow_dca,
            allow_rebalance=True,
            status="active",
        )
        db.session.add(assignment)
        db.session.commit()
        return assignment

    def create_market_data(
        instrument_id: int,
        trade_date: date,
        open: float | None = None,
        high: float | None = None,
        low: float | None = None,
        close: float | None = None,
        prev_close: float | None = None,
        nav: float | None = None,
        acc_nav: float | None = None,
        est_nav: float | None = None,
        iopv: float | None = None,
        ma20: float | None = None,
        ma60: float | None = None,
        ma120: float | None = None,
        atr14: float | None = None,
        volatility_20d: float | None = None,
        return_5d: float | None = None,
        return_20d: float | None = None,
        return_60d: float | None = None,
        breakout_high_20d: float | None = None,
        breakdown_low_20d: float | None = None,
        drawdown_60d: float | None = None,
        max_drawdown_120d: float | None = None,
        relative_strength_20d: float | None = None,
        volume: float | None = None,
        amount: float | None = None,
        turnover_rate: float | None = None,
        amplitude: float | None = None,
        open_gap_pct: float | None = None,
        premium_discount_pct: float | None = None,
        premium_discount_zscore_20d: float | None = None,
        volume_ma20: float | None = None,
        volume_ratio_5d: float | None = None,
        **extra_fields,
    ) -> MarketData:
        row = MarketData(
            instrument_id=instrument_id,
            trade_date=trade_date,
            open=open,
            high=high,
            low=low,
            close=close,
            prev_close=prev_close,
            nav=nav,
            acc_nav=acc_nav,
            est_nav=est_nav,
            iopv=iopv,
            ma20=ma20,
            ma60=ma60,
            ma120=ma120,
            atr14=atr14,
            volatility_20d=volatility_20d,
            return_5d=return_5d,
            return_20d=return_20d,
            return_60d=return_60d,
            breakout_high_20d=breakout_high_20d,
            breakdown_low_20d=breakdown_low_20d,
            drawdown_60d=drawdown_60d,
            max_drawdown_120d=max_drawdown_120d,
            relative_strength_20d=relative_strength_20d,
            volume=volume,
            amount=amount,
            turnover_rate=turnover_rate,
            amplitude=amplitude,
            open_gap_pct=open_gap_pct,
            premium_discount_pct=premium_discount_pct,
            premium_discount_zscore_20d=premium_discount_zscore_20d,
            volume_ma20=volume_ma20,
            volume_ratio_5d=volume_ratio_5d,
            **extra_fields,
        )
        db.session.add(row)
        db.session.commit()
        return row

    def create_position(
        account_id: int,
        instrument_id: int,
        quantity: float,
        avg_cost: float,
        market_price: float,
        weight_in_account: float = 0.0,
    ) -> Position:
        position = Position(
            account_id=account_id,
            instrument_id=instrument_id,
            quantity=quantity,
            avg_cost=avg_cost,
            market_price=market_price,
            weight_in_account=weight_in_account,
            position_status="open",
        )
        position.update_market_value()
        db.session.add(position)
        db.session.commit()
        return position

    return SimpleNamespace(
        create_account=create_account,
        create_template=create_template,
        create_instrument=create_instrument,
        create_assignment=create_assignment,
        create_market_data=create_market_data,
        create_position=create_position,
    )


def json_dumps(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)
