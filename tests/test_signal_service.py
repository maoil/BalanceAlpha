from datetime import date

from app.services.signal_service import SignalService
from app.utils.constants import SignalType


def test_generate_core_signal_returns_rebalance_when_position_is_overweight(app, factories):
    account = factories.create_account(
        account_code="core-signal",
        account_name="核心信号",
        account_type="core",
    )
    template = factories.create_template(
        template_code="core_index_template",
        template_name="核心宽基",
        account_type="core",
        config={"cash_buffer_lower": 0.05, "cash_buffer_upper": 0.10},
    )
    instrument = factories.create_instrument(symbol="513110", name="纳指100ETF")
    assignment = factories.create_assignment(
        account_id=account.id,
        instrument_id=instrument.id,
        template_id=template.id,
        lower=0.20,
        upper=0.24,
    )
    factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=100,
        avg_cost=10,
        market_price=12,
        weight_in_account=0.30,
    )
    factories.create_market_data(
        instrument_id=instrument.id,
        trade_date=date(2025, 4, 1),
        close=12,
        ma60=11,
        drawdown_60d=-0.12,
    )

    signal = SignalService._generate_core_signal(
        signal_date=date(2025, 4, 1),
        account=account,
        instrument=instrument,
        assignment=assignment,
        batch_id="test",
        batch_version=1,
    )

    assert signal.signal_type == SignalType.REBALANCE.value


def test_generate_tactical_signal_handles_buy_and_stop_loss_branches(app, factories):
    account = factories.create_account(
        account_code="tactical-signal",
        account_name="战术信号",
        account_type="tactical",
    )
    template = factories.create_template(
        template_code="tactical_theme_template",
        template_name="战术动能趋势策略",
        account_type="tactical",
        version="2.1",
        config={
            "ma_short": 20,
            "ma_long": 60,
            "initial_position_pct": 0.40,
            "add_confirm_pct": 0.05,
            "add_position_pct": 0.30,
            "entry_rs_threshold": 0.00,
            "stop_loss_warn_pct": -0.05,
            "stop_loss_warn_reduce_ratio": 0.25,
            "stop_loss_pct": -0.08,
            "stop_loss_reduce_ratio": 0.50,
            "stop_loss_clear_pct": -0.10,
            "early_exit_pct": -0.06,
            "profit_protect_trigger_pct": 0.09,
            "profit_protect_reduce_ratio": 0.20,
            "take_profit_pct_1": 0.12,
            "take_profit_pct_2": 0.18,
            "take_profit_pct_3": 0.25,
            "take_profit_sell_ratio_1": 0.20,
            "take_profit_sell_ratio_2": 0.30,
            "take_profit_sell_ratio_3": 0.30,
        },
    )
    instrument = factories.create_instrument(symbol="159819", name="人工智能ETF")
    assignment = factories.create_assignment(
        account_id=account.id,
        instrument_id=instrument.id,
        template_id=template.id,
        lower=0.10,
        upper=0.30,
    )

    factories.create_market_data(
        instrument_id=instrument.id,
        trade_date=date(2025, 4, 1),
        close=1.2,
        ma20=1.1,
        ma60=1.0,
        relative_strength_20d=0.05,
    )

    buy_signal = SignalService._generate_tactical_signal(
        signal_date=date(2025, 4, 1),
        account=account,
        instrument=instrument,
        assignment=assignment,
        batch_id="test",
        batch_version=1,
    )
    assert buy_signal.signal_type == SignalType.ALLOW_BUY.value

    factories.create_position(
        account_id=account.id,
        instrument_id=instrument.id,
        quantity=100,
        avg_cost=1.0,
        market_price=0.88,
        weight_in_account=0.20,
    )
    factories.create_market_data(
        instrument_id=instrument.id,
        trade_date=date(2025, 4, 2),
        close=0.88,
        ma20=0.95,
        ma60=1.02,
        relative_strength_20d=-0.08,
    )

    stop_signal = SignalService._generate_tactical_signal(
        signal_date=date(2025, 4, 2),
        account=account,
        instrument=instrument,
        assignment=assignment,
        batch_id="test",
        batch_version=2,
    )
    assert stop_signal.signal_type == SignalType.STOP_LOSS.value
