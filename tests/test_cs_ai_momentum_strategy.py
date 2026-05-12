import pandas as pd

from app.backtesting.strategies.cs_ai_momentum import add_cs_ai_indicators


def test_cs_ai_donchian_channels_use_close_prices():
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    data = pd.DataFrame(
        {
            "Open": [1.0] * 10,
            "High": [100.0] * 10,
            "Low": [-100.0] * 10,
            "Close": list(range(1, 11)),
            "Volume": [1000] * 10,
        },
        index=dates,
    )

    result = add_cs_ai_indicators(data)

    assert result["HH10"].iloc[-1] == 10
    assert result["LL10"].iloc[-1] == 1
