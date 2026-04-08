"""
行情数据服务
"""
import csv
import logging
from typing import Optional
from datetime import date
from pathlib import Path

import pandas as pd

from app.extensions import db
from app.models.market_data import MarketData
from app.models.instrument import Instrument
from app.services.log_service import LogService

logger = logging.getLogger(__name__)


class MarketDataService:
    """行情数据业务逻辑"""

    @staticmethod
    def get_latest(instrument_id: int) -> Optional[MarketData]:
        """获取产品最新行情"""
        return MarketData.query.filter_by(
            instrument_id=instrument_id
        ).order_by(MarketData.trade_date.desc()).first()

    @staticmethod
    def get_history(
        instrument_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[MarketData]:
        """获取历史行情"""
        query = MarketData.query.filter_by(instrument_id=instrument_id)
        if start_date:
            query = query.filter(MarketData.trade_date >= start_date)
        if end_date:
            query = query.filter(MarketData.trade_date <= end_date)
        return query.order_by(MarketData.trade_date).all()

    @staticmethod
    def get_history_df(instrument_id: int) -> pd.DataFrame:
        """获取历史行情为 DataFrame，用于策略计算"""
        records = MarketData.query.filter_by(
            instrument_id=instrument_id
        ).order_by(MarketData.trade_date).all()

        if not records:
            return pd.DataFrame()

        data = []
        for r in records:
            data.append({
                "trade_date": r.trade_date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "nav": r.nav,
                "acc_nav": r.acc_nav,
                "ma20": r.ma20,
                "ma60": r.ma60,
                "ma120": r.ma120,
            })
        df = pd.DataFrame(data)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df.set_index("trade_date", inplace=True)
        return df

    @staticmethod
    def import_csv(file_path: str, instrument_id: int) -> dict:
        """
        从 CSV 文件导入行情数据

        CSV 格式要求（表头）:
        trade_date, open, high, low, close, volume, nav, acc_nav

        - 场外基金可只有 trade_date, nav, acc_nav
        - 场内 ETF/LOF 应有 OHLCV

        Returns:
            {"imported": 数量, "skipped": 数量, "errors": [错误列表]}
        """
        result = {"imported": 0, "skipped": 0, "errors": []}

        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            result["errors"].append(f"读取 CSV 失败: {str(e)}")
            return result

        # 标准化列名（去空格、转小写）
        df.columns = [c.strip().lower() for c in df.columns]

        if "trade_date" not in df.columns:
            result["errors"].append("CSV 缺少 trade_date 列")
            return result

        for _, row in df.iterrows():
            try:
                trade_date_val = pd.to_datetime(row["trade_date"]).date()

                # 检查是否已存在
                existing = MarketData.query.filter_by(
                    instrument_id=instrument_id,
                    trade_date=trade_date_val,
                ).first()
                if existing:
                    result["skipped"] += 1
                    continue

                md = MarketData(
                    instrument_id=instrument_id,
                    trade_date=trade_date_val,
                    open=row.get("open"),
                    high=row.get("high"),
                    low=row.get("low"),
                    close=row.get("close"),
                    volume=row.get("volume"),
                    nav=row.get("nav"),
                    acc_nav=row.get("acc_nav"),
                )
                db.session.add(md)
                result["imported"] += 1

            except Exception as e:
                result["errors"].append(f"行 {row.get('trade_date', '?')}: {str(e)}")

        db.session.commit()

        # 导入后计算技术指标
        if result["imported"] > 0:
            MarketDataService.calculate_indicators(instrument_id)

        LogService.log(
            log_type="data_import",
            level="info",
            module="market_data",
            message=f"导入行情: instrument_id={instrument_id}, 导入={result['imported']}, 跳过={result['skipped']}",
            context=result,
        )

        return result

    @staticmethod
    def calculate_indicators(instrument_id: int) -> None:
        """
        计算技术指标：MA20, MA60, MA120, 60日回撤

        使用 pandas 批量计算后写回数据库
        """
        records = MarketData.query.filter_by(
            instrument_id=instrument_id
        ).order_by(MarketData.trade_date).all()

        if len(records) < 5:
            return

        # 使用收盘价或净值作为价格序列
        prices = []
        for r in records:
            price = r.close if r.close else r.nav
            prices.append(price if price else 0)

        prices_series = pd.Series(prices)

        # 计算均线
        ma20 = prices_series.rolling(window=20, min_periods=1).mean()
        ma60 = prices_series.rolling(window=60, min_periods=1).mean()
        ma120 = prices_series.rolling(window=120, min_periods=1).mean()

        # 计算 60 日回撤 = (当前价 - 60日最高价) / 60日最高价
        high_60d = prices_series.rolling(window=60, min_periods=1).max()
        drawdown_60d = (prices_series - high_60d) / high_60d

        # 计算 20 日相对强弱 (简单动量: 当前价/20日前价 - 1)
        rs_20d = prices_series.pct_change(periods=20)

        # 写回
        for i, record in enumerate(records):
            record.ma20 = round(ma20.iloc[i], 4) if pd.notna(ma20.iloc[i]) else None
            record.ma60 = round(ma60.iloc[i], 4) if pd.notna(ma60.iloc[i]) else None
            record.ma120 = round(ma120.iloc[i], 4) if pd.notna(ma120.iloc[i]) else None
            record.drawdown_60d = round(drawdown_60d.iloc[i], 4) if pd.notna(drawdown_60d.iloc[i]) else None
            record.relative_strength_20d = round(rs_20d.iloc[i], 4) if pd.notna(rs_20d.iloc[i]) else None

        db.session.commit()
        logger.info(f"计算技术指标完成: instrument_id={instrument_id}, 记录数={len(records)}")

    @staticmethod
    def add_single(instrument_id: int, data: dict) -> MarketData:
        """手动添加单条行情数据"""
        md = MarketData(
            instrument_id=instrument_id,
            trade_date=data["trade_date"],
            open=data.get("open"),
            high=data.get("high"),
            low=data.get("low"),
            close=data.get("close"),
            volume=data.get("volume"),
            nav=data.get("nav"),
            acc_nav=data.get("acc_nav"),
        )
        db.session.add(md)
        db.session.commit()
        return md
