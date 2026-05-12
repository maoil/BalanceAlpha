from datetime import date

import pandas as pd

from app.backtesting.registry import get_config_by_key
from app.extensions import db
from app.services import strategy_signal_service as signal_service_module
from app.services.strategy_signal_service import StrategySignalService


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 5, 12)


def test_strategy_signal_separates_signal_date_from_execution_date(
    app, factories, monkeypatch
):
    instrument = factories.create_instrument(
        symbol="012734",
        name="易方达人工智能ETF联接C",
        instrument_type="fund",
        trade_mode="eod_nav",
    )
    instrument.backtest_config_key = "cs_ai_momentum"
    db.session.commit()

    index = pd.date_range("2026-04-01", "2026-05-11", freq="D")
    close = [1.0 + i * 0.01 for i in range(len(index))]
    fake_data = pd.DataFrame(
        {
            "Open": close,
            "High": close,
            "Low": close,
            "Close": close,
            "Volume": [0] * len(index),
        },
        index=index,
    )

    config = get_config_by_key("cs_ai_momentum")
    monkeypatch.setattr(config, "provider", lambda *args, **kwargs: fake_data)
    monkeypatch.setattr(signal_service_module, "date", FixedDate)

    result = StrategySignalService.generate_signal_for_instrument(instrument.id)

    assert result["signal_date"] == "2026-05-11"
    assert result["execution_date"] == "2026-05-12"
    assert result["execution_timing"] == "T+1 15:00前"
    assert result["execution_price_known"] is False
    assert "执行日净值" in result["execution_price_note"]
    assert result["risk_filter"]["enabled"] is True
    assert result["risk_filter"]["source"] == "fund_nav"
