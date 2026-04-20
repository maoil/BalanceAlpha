"""
Market data service.
"""
import logging
from datetime import date
from typing import Optional

import pandas as pd

from app.extensions import db
from app.models.market_data import MarketData
from app.services.log_service import LogService

logger = logging.getLogger(__name__)


class MarketDataService:
    """Market data business logic."""

    HISTORY_COLUMNS = (
        "open",
        "high",
        "low",
        "close",
        "prev_close",
        "volume",
        "amount",
        "turnover_rate",
        "amplitude",
        "open_gap_pct",
        "nav",
        "acc_nav",
        "est_nav",
        "iopv",
        "premium_discount_pct",
        "premium_discount_zscore_20d",
        "ma20",
        "ma60",
        "ma120",
        "atr14",
        "volatility_20d",
        "return_5d",
        "return_20d",
        "return_60d",
        "breakout_high_20d",
        "breakdown_low_20d",
        "drawdown_60d",
        "max_drawdown_120d",
        "relative_strength_20d",
        "volume_ma20",
        "volume_ratio_5d",
    )

    IMPORT_FIELDS = (
        "open",
        "high",
        "low",
        "close",
        "prev_close",
        "volume",
        "amount",
        "turnover_rate",
        "amplitude",
        "open_gap_pct",
        "nav",
        "acc_nav",
        "est_nav",
        "iopv",
        "premium_discount_pct",
    )

    @staticmethod
    def get_latest(instrument_id: int) -> Optional[MarketData]:
        """Get latest market data row for one instrument."""
        return MarketData.query.filter_by(
            instrument_id=instrument_id
        ).order_by(MarketData.trade_date.desc()).first()

    @staticmethod
    def get_history(
        instrument_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[MarketData]:
        """Get historical market data rows."""
        query = MarketData.query.filter_by(instrument_id=instrument_id)
        if start_date:
            query = query.filter(MarketData.trade_date >= start_date)
        if end_date:
            query = query.filter(MarketData.trade_date <= end_date)
        return query.order_by(MarketData.trade_date).all()

    @staticmethod
    def get_history_df(instrument_id: int) -> pd.DataFrame:
        """Get historical market data as a DataFrame for strategy logic."""
        records = MarketData.query.filter_by(
            instrument_id=instrument_id
        ).order_by(MarketData.trade_date).all()

        if not records:
            return pd.DataFrame()

        data = []
        for record in records:
            row = {"trade_date": record.trade_date}
            for field in MarketDataService.HISTORY_COLUMNS:
                row[field] = getattr(record, field)
            data.append(row)

        df = pd.DataFrame(data)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df.set_index("trade_date", inplace=True)
        return df

    @staticmethod
    def import_csv(file_path: str, instrument_id: int) -> dict:
        """
        Import market data from a CSV file.

        Required column:
        trade_date
        """
        result = {"imported": 0, "updated": 0, "skipped": 0, "errors": []}

        try:
            df = pd.read_csv(file_path)
        except Exception as exc:
            result["errors"].append(f"读取 CSV 失败: {str(exc)}")
            return result

        df.columns = [column.strip().lower() for column in df.columns]

        if "trade_date" not in df.columns:
            result["errors"].append("CSV 缺少 trade_date 列")
            return result

        for _, row in df.iterrows():
            try:
                trade_date_value = pd.to_datetime(row["trade_date"]).date()
                payload = MarketDataService._extract_payload(row)
                existing = MarketData.query.filter_by(
                    instrument_id=instrument_id,
                    trade_date=trade_date_value,
                ).first()

                if existing:
                    changed = MarketDataService._apply_payload(existing, payload)
                    if changed:
                        result["updated"] += 1
                    else:
                        result["skipped"] += 1
                    continue

                market_data = MarketData(
                    instrument_id=instrument_id,
                    trade_date=trade_date_value,
                    **payload,
                )
                db.session.add(market_data)
                result["imported"] += 1
            except Exception as exc:
                result["errors"].append(f"行 {row.get('trade_date', '?')}: {str(exc)}")

        db.session.commit()

        if result["imported"] > 0 or result["updated"] > 0:
            MarketDataService.calculate_indicators(instrument_id)

        LogService.log(
            log_type="data_import",
            level="info",
            module="market_data",
            message=(
                f"导入行情: instrument_id={instrument_id}, "
                f"导入={result['imported']}, 更新={result['updated']}, 跳过={result['skipped']}"
            ),
            context=result,
        )

        return result

    @staticmethod
    def calculate_indicators(instrument_id: int) -> None:
        """Calculate raw helpers and derived indicators for one instrument."""
        records = MarketData.query.filter_by(
            instrument_id=instrument_id
        ).order_by(MarketData.trade_date).all()

        if not records:
            return

        frame = pd.DataFrame([
            {
                "trade_date": record.trade_date,
                "open": record.open,
                "high": record.high,
                "low": record.low,
                "close": record.close,
                "prev_close": record.prev_close,
                "volume": record.volume,
                "amount": record.amount,
                "turnover_rate": record.turnover_rate,
                "amplitude": record.amplitude,
                "open_gap_pct": record.open_gap_pct,
                "nav": record.nav,
                "acc_nav": record.acc_nav,
                "est_nav": record.est_nav,
                "iopv": record.iopv,
                "premium_discount_pct": record.premium_discount_pct,
            }
            for record in records
        ])

        if frame.empty:
            return

        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        frame.sort_values("trade_date", inplace=True)
        frame.reset_index(drop=True, inplace=True)

        numeric_columns = [
            column for column in frame.columns
            if column != "trade_date"
        ]
        for column in numeric_columns:
            frame[column] = pd.to_numeric(
                frame[column].map(MarketDataService._to_float),
                errors="coerce",
            )

        close_series = MarketDataService._positive_series(frame["close"])
        nav_series = MarketDataService._positive_series(frame["nav"])
        est_nav_series = MarketDataService._positive_series(frame["est_nav"])
        iopv_series = MarketDataService._positive_series(frame["iopv"])

        price_series = close_series.fillna(nav_series).fillna(est_nav_series).fillna(iopv_series)
        prev_close_series = MarketDataService._positive_series(frame["prev_close"]).fillna(price_series.shift(1))
        high_series = MarketDataService._positive_series(frame["high"]).fillna(price_series)
        low_series = MarketDataService._positive_series(frame["low"]).fillna(price_series)
        open_series = MarketDataService._positive_series(frame["open"])

        reference_nav_series = nav_series.fillna(est_nav_series).fillna(iopv_series)

        ma20 = price_series.rolling(window=20, min_periods=1).mean()
        ma60 = price_series.rolling(window=60, min_periods=1).mean()
        ma120 = price_series.rolling(window=120, min_periods=1).mean()

        rolling_high_60 = price_series.rolling(window=60, min_periods=1).max()
        drawdown_60d = (price_series / rolling_high_60) - 1

        previous_high_20 = price_series.shift(1).rolling(window=20, min_periods=1).max()
        previous_low_20 = price_series.shift(1).rolling(window=20, min_periods=1).min()
        breakout_high_20d = (price_series / previous_high_20) - 1
        breakdown_low_20d = (price_series / previous_low_20) - 1

        returns = price_series.pct_change()
        rs_20d = price_series.pct_change(periods=20)
        return_5d = price_series.pct_change(periods=5)
        return_20d = price_series.pct_change(periods=20)
        return_60d = price_series.pct_change(periods=60)
        volatility_20d = returns.rolling(window=20, min_periods=5).std(ddof=0) * (252 ** 0.5)

        true_range = pd.concat(
            [
                high_series - low_series,
                (high_series - prev_close_series).abs(),
                (low_series - prev_close_series).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr14 = true_range.rolling(window=14, min_periods=1).mean()

        volume_series = frame["volume"].where(frame["volume"] >= 0)
        volume_ma20 = volume_series.rolling(window=20, min_periods=1).mean()
        previous_volume_ma5 = volume_series.shift(1).rolling(window=5, min_periods=1).mean()
        volume_ratio_5d = volume_series / previous_volume_ma5
        volume_ratio_5d = volume_ratio_5d.where(previous_volume_ma5 > 0)

        amplitude = (high_series - low_series) / prev_close_series
        amplitude = amplitude.where(prev_close_series > 0)
        open_gap_pct = (open_series / prev_close_series) - 1
        open_gap_pct = open_gap_pct.where((open_series > 0) & (prev_close_series > 0))

        premium_discount_pct = (price_series / reference_nav_series) - 1
        premium_discount_pct = premium_discount_pct.where(reference_nav_series > 0)
        premium_mean_20 = premium_discount_pct.rolling(window=20, min_periods=5).mean()
        premium_std_20 = premium_discount_pct.rolling(window=20, min_periods=5).std(ddof=0)
        premium_discount_zscore_20d = (premium_discount_pct - premium_mean_20) / premium_std_20
        premium_discount_zscore_20d = premium_discount_zscore_20d.where(premium_std_20 > 0, 0.0)
        premium_discount_zscore_20d = premium_discount_zscore_20d.where(premium_discount_pct.notna())

        max_drawdown_120d = price_series.rolling(window=120, min_periods=1).apply(
            MarketDataService._window_max_drawdown,
            raw=False,
        )

        for index, record in enumerate(records):
            record.prev_close = MarketDataService._round(prev_close_series.iloc[index])
            record.amplitude = MarketDataService._round(amplitude.iloc[index])
            record.open_gap_pct = MarketDataService._round(open_gap_pct.iloc[index])
            record.premium_discount_pct = MarketDataService._round(premium_discount_pct.iloc[index])
            record.premium_discount_zscore_20d = MarketDataService._round(
                premium_discount_zscore_20d.iloc[index]
            )
            record.ma20 = MarketDataService._round(ma20.iloc[index])
            record.ma60 = MarketDataService._round(ma60.iloc[index])
            record.ma120 = MarketDataService._round(ma120.iloc[index])
            record.atr14 = MarketDataService._round(atr14.iloc[index])
            record.volatility_20d = MarketDataService._round(volatility_20d.iloc[index])
            record.return_5d = MarketDataService._round(return_5d.iloc[index])
            record.return_20d = MarketDataService._round(return_20d.iloc[index])
            record.return_60d = MarketDataService._round(return_60d.iloc[index])
            record.breakout_high_20d = MarketDataService._round(breakout_high_20d.iloc[index])
            record.breakdown_low_20d = MarketDataService._round(breakdown_low_20d.iloc[index])
            record.drawdown_60d = MarketDataService._round(drawdown_60d.iloc[index])
            record.max_drawdown_120d = MarketDataService._round(max_drawdown_120d.iloc[index])
            record.relative_strength_20d = MarketDataService._round(rs_20d.iloc[index])
            record.volume_ma20 = MarketDataService._round(volume_ma20.iloc[index])
            record.volume_ratio_5d = MarketDataService._round(volume_ratio_5d.iloc[index])

        db.session.commit()
        logger.info(
            "Calculated market indicators: instrument_id=%s, rows=%s",
            instrument_id,
            len(records),
        )

    @staticmethod
    def add_single(instrument_id: int, data: dict) -> MarketData:
        """Insert a single market data row."""
        payload = MarketDataService._extract_payload(data)
        market_data = MarketData(
            instrument_id=instrument_id,
            trade_date=data["trade_date"],
            **payload,
        )
        db.session.add(market_data)
        db.session.commit()
        return market_data

    @staticmethod
    def _extract_payload(row: dict | pd.Series) -> dict:
        payload = {}
        for field in MarketDataService.IMPORT_FIELDS:
            payload[field] = MarketDataService._to_float(row.get(field))
        return payload

    @staticmethod
    def _apply_payload(record: MarketData, payload: dict) -> bool:
        changed = False
        for field, value in payload.items():
            if value is None:
                continue
            if getattr(record, field) != value:
                setattr(record, field, value)
                changed = True
        return changed

    @staticmethod
    def _to_float(value: object) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.replace(",", "").replace("%", "").strip()
            if not value or value in {"--", "None", "nan", "NaN"}:
                return None
        if pd.isna(value):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _positive_series(series: pd.Series) -> pd.Series:
        return series.where(series > 0)

    @staticmethod
    def _round(value: object, digits: int = 4) -> Optional[float]:
        if value is None or pd.isna(value):
            return None
        return round(float(value), digits)

    @staticmethod
    def _window_max_drawdown(window: pd.Series) -> float:
        if window is None or len(window) == 0:
            return 0.0
        drawdown = window / window.cummax() - 1
        return float(drawdown.min())
