from datetime import date

from app.services.backtest_service import BacktestService


def test_backtest_service_runs_tactical_strategy_and_records_trades(app, factories):
    account = factories.create_account(
        account_code="tactical-bt",
        account_name="战术回测",
        account_type="tactical",
    )
    template = factories.create_template(
        template_code="tactical_theme_template",
        template_name="战术动能趋势策略",
        account_type="tactical",
        version="2.1",
        config={
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
    factories.create_assignment(
        account_id=account.id,
        instrument_id=instrument.id,
        template_id=template.id,
        lower=0.10,
        upper=0.30,
    )

    factories.create_market_data(
        instrument_id=instrument.id,
        trade_date=date(2025, 3, 31),
        close=0.98,
        ma20=0.94,
        ma60=0.89,
        relative_strength_20d=0.02,
    )
    factories.create_market_data(
        instrument_id=instrument.id,
        trade_date=date(2025, 4, 1),
        close=1.00,
        ma20=0.95,
        ma60=0.90,
        relative_strength_20d=0.03,
    )
    factories.create_market_data(
        instrument_id=instrument.id,
        trade_date=date(2025, 4, 2),
        close=1.08,
        ma20=1.00,
        ma60=0.92,
        relative_strength_20d=0.06,
    )
    factories.create_market_data(
        instrument_id=instrument.id,
        trade_date=date(2025, 4, 3),
        close=1.24,
        ma20=1.08,
        ma60=0.98,
        relative_strength_20d=0.12,
    )

    run = BacktestService.run_backtest(
        run_name="战术单品种回测",
        account_id=account.id,
        instrument_id=instrument.id,
        template_id=template.id,
        start_date=date(2025, 4, 1),
        end_date=date(2025, 4, 3),
        initial_capital=100000,
        fee_rate=0.0,
    )

    result = BacktestService.parse_result(run)
    summary = result["summary"]
    trades = result["trades"]

    assert run.status == "completed"
    assert summary["trade_count"] >= 2
    assert summary["total_return"] > 0
    assert result["history_coverage"]["has_warnings"] is True
    assert all(trade["date"] >= "2025-04-01" for trade in trades)
    assert any(trade["action"] == "buy" for trade in trades)
    assert any(trade["action"] == "sell" for trade in trades)


def test_backtest_service_does_not_repeat_take_profit_for_the_same_stage(app, factories):
    account = factories.create_account(
        account_code="tactical-stage",
        account_name="战术阶段回测",
        account_type="tactical",
    )
    template = factories.create_template(
        template_code="tactical_theme_template",
        template_name="战术动能趋势策略",
        account_type="tactical",
        version="2.1",
        config={
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
    instrument = factories.create_instrument(symbol="159999", name="阶段测试ETF")
    factories.create_assignment(
        account_id=account.id,
        instrument_id=instrument.id,
        template_id=template.id,
        lower=0.10,
        upper=0.30,
    )

    prices = [1.00, 1.08, 1.20, 1.30, 1.36, 1.40, 1.42, 1.41]
    for offset, price in enumerate(prices):
        factories.create_market_data(
            instrument_id=instrument.id,
            trade_date=date(2025, 5, 1 + offset),
            close=price,
            ma20=max(0.95, price * 0.96),
            ma60=max(0.90, price * 0.90),
            relative_strength_20d=0.08,
        )

    run = BacktestService.run_backtest(
        run_name="阶段止盈回测",
        account_id=account.id,
        instrument_id=instrument.id,
        template_id=template.id,
        start_date=date(2025, 5, 1),
        end_date=date(2025, 5, 8),
        initial_capital=100000,
        fee_rate=0.0,
    )

    result = BacktestService.parse_result(run)
    trades = result["trades"]
    take_profit_reasons = [
        trade["reason_code"]
        for trade in trades
        if trade["action"] == "sell" and trade["reason_code"].startswith("tactical_take_profit_")
    ]

    assert take_profit_reasons.count("tactical_take_profit_1") == 1
    assert take_profit_reasons.count("tactical_take_profit_2") == 1
    assert take_profit_reasons.count("tactical_take_profit_3") == 1
