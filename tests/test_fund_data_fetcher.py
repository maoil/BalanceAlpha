import pytest
import pandas as pd

from app.services.fund_data_fetcher import FundDataFetcher


def test_build_history_indicators_calculates_multiple_metrics():
    prices = [100 + idx for idx in range(260)]
    history_df = pd.DataFrame(
        {
            "trade_date": pd.date_range("2025-01-01", periods=len(prices), freq="B"),
            "close": prices,
        }
    )

    indicators = FundDataFetcher._build_history_indicators(history_df)

    assert indicators["data_points"] == 260
    assert indicators["ma20"] == pytest.approx(sum(prices[-20:]) / 20, rel=1e-4)
    assert indicators["ma60"] == pytest.approx(sum(prices[-60:]) / 60, rel=1e-4)
    assert indicators["ma120"] == pytest.approx(sum(prices[-120:]) / 120, rel=1e-4)
    assert indicators["return_1m"] == pytest.approx(round(prices[-1] / prices[-21] - 1, 4), abs=1e-6)
    assert indicators["return_3m"] == pytest.approx(round(prices[-1] / prices[-61] - 1, 4), abs=1e-6)
    assert indicators["return_6m"] == pytest.approx(round(prices[-1] / prices[-121] - 1, 4), abs=1e-6)
    assert indicators["return_1y"] == pytest.approx(round(prices[-1] / prices[-251] - 1, 4), abs=1e-6)
    assert indicators["drawdown_60d"] == pytest.approx(0.0, abs=1e-6)


def test_get_fund_info_aggregates_quote_and_indicators(monkeypatch):
    monkeypatch.setattr(
        FundDataFetcher,
        "_get_basic_fund_info",
        lambda fund_code: {
            "基金全称": "纳指100ETF",
            "基金简称": "纳指100ETF",
            "基金类型": "QDII-ETF",
            "基金经理": "测试经理",
            "基金公司": "测试基金",
            "成立日期": "2020-01-01",
            "业绩比较基准": "纳斯达克100指数",
        },
    )
    monkeypatch.setattr(FundDataFetcher, "_get_fund_info_em", lambda fund_code: {})
    monkeypatch.setattr(
        FundDataFetcher,
        "_build_quote_snapshot",
        lambda fund_code, trade_mode: {
            "source": "sina_etf",
            "latest_price": 1.2345,
            "latest_nav": 1.2100,
            "estimated_nav": 1.2380,
            "change_pct": 1.23,
            "quote_date": "2026-04-20",
            "quote_time": "15:00:00",
        },
    )
    monkeypatch.setattr(
        FundDataFetcher,
        "_get_history_indicators",
        lambda fund_code, trade_mode: {
            "source": "etf_history",
            "ma20": 1.1111,
            "return_1m": 0.0567,
        },
    )

    info = FundDataFetcher.get_fund_info("159941")

    assert info["code"] == "159941"
    assert info["name"] == "纳指100ETF"
    assert info["short_name"] == "纳指100ETF"
    assert info["instrument_type"] == "etf"
    assert info["trade_mode"] == "exchange_traded"
    assert info["latest_price"] == pytest.approx(1.2345)
    assert info["nav"] == pytest.approx(1.21)
    assert info["est_nav"] == pytest.approx(1.238)
    assert info["change_pct"] == pytest.approx(1.23)
    assert info["quote"]["source"] == "sina_etf"
    assert info["indicators"]["ma20"] == pytest.approx(1.1111)
    assert info["indicators"]["return_1m"] == pytest.approx(0.0567)
