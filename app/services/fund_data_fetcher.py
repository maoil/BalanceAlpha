"""
基金/ETF 数据抓取服务

从公开数据源（东方财富/天天基金）获取：
1. 基金基本信息（名称、类型、净值等）
2. 实时估值/最新净值
3. 历史净值/行情数据
4. ETF 实时价格

使用 akshare 库 + 东方财富公开接口
"""
import json
import logging
import requests
from typing import Optional
from datetime import date, datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)

# 请求头，模拟浏览器
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://fund.eastmoney.com/",
}


class FundDataFetcher:
    """基金/ETF 数据抓取"""

    @staticmethod
    def search_fund(keyword: str) -> list[dict]:
        """
        按关键词搜索基金（支持代码或名称）

        使用东方财富基金搜索接口

        Args:
            keyword: 基金代码或名称关键词
        Returns:
            匹配的基金列表 [{"code", "name", "type"}, ...]
        """
        try:
            url = "https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx"
            params = {
                "m": "1",
                "key": keyword,
                "pageindex": "1",
                "pagesize": "20",
            }
            resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            results = []
            if data and "Datas" in data:
                for item in data["Datas"]:
                    # 类型映射
                    fund_type_map = {
                        "1": "fund",   # 股票型/混合型
                        "2": "fund",   # 货币型
                        "3": "fund",   # 债券型
                        "4": "etf",    # ETF
                        "5": "etf",    # QDII
                        "6": "lof",    # LOF
                        "7": "fund",   # FOF
                    }
                    results.append({
                        "code": item.get("CODE", ""),
                        "name": item.get("NAME", "").replace("<em>", "").replace("</em>", ""),
                        "type": fund_type_map.get(str(item.get("FundType", "")), "fund"),
                        "pinyin": item.get("PINYIN", ""),
                    })
            return results

        except Exception as e:
            logger.error(f"搜索基金失败: {e}")
            # 备选方案：用 akshare
            return FundDataFetcher._search_fund_akshare(keyword)

    @staticmethod
    def _search_fund_akshare(keyword: str) -> list[dict]:
        """使用 akshare 搜索基金（备选方案）"""
        try:
            import akshare as ak
            # 获取所有基金列表
            df = ak.fund_name_em()
            # 模糊匹配
            mask = (
                df["基金代码"].str.contains(keyword, case=False, na=False) |
                df["基金简称"].str.contains(keyword, case=False, na=False)
            )
            matched = df[mask].head(20)

            results = []
            for _, row in matched.iterrows():
                fund_type = "fund"
                name = str(row.get("基金简称", ""))
                if "ETF" in name.upper():
                    fund_type = "etf"
                elif "LOF" in name.upper():
                    fund_type = "lof"

                results.append({
                    "code": str(row.get("基金代码", "")),
                    "name": name,
                    "type": fund_type,
                    "pinyin": str(row.get("拼音缩写", "")),
                })
            return results
        except Exception as e:
            logger.error(f"akshare 搜索基金失败: {e}")
            return []

    @staticmethod
    def get_fund_info(fund_code: str) -> Optional[dict]:
        """
        获取基金详细信息

        Args:
            fund_code: 基金代码，如 "159941"
        Returns:
            基金信息字典
        """
        try:
            import akshare as ak
            # 获取基金基本信息
            info_df = ak.fund_individual_basic_info_xq(symbol=fund_code)
            info = {}
            if info_df is not None and len(info_df) > 0:
                for _, row in info_df.iterrows():
                    key = str(row.iloc[0]).strip()
                    val = str(row.iloc[1]).strip()
                    info[key] = val

            return {
                "code": fund_code,
                "name": info.get("基金全称", info.get("基金简称", fund_code)),
                "short_name": info.get("基金简称", ""),
                "type": info.get("基金类型", ""),
                "manager": info.get("基金经理", ""),
                "company": info.get("基金公司", info.get("管理人", "")),
                "inception_date": info.get("成立日期", ""),
                "benchmark": info.get("业绩比较基准", ""),
                "raw_info": info,
            }
        except Exception as e:
            logger.warning(f"akshare 获取基金信息失败: {e}，使用备选方案")
            return FundDataFetcher._get_fund_info_em(fund_code)

    @staticmethod
    def _get_fund_info_em(fund_code: str) -> Optional[dict]:
        """使用东方财富接口获取基金信息（备选方案）"""
        try:
            url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200 and "jsonpgz" in resp.text:
                data_str = resp.text.strip().replace("jsonpgz(", "").rstrip(");")
                data = json.loads(data_str)
                return {
                    "code": data.get("fundcode", fund_code),
                    "name": data.get("name", ""),
                    "short_name": data.get("name", ""),
                    "type": "",
                    "nav": float(data.get("dwjz", 0)),
                    "est_nav": float(data.get("gsz", 0)),
                    "est_change_pct": data.get("gszzl", "0"),
                    "nav_date": data.get("jzrq", ""),
                }
        except Exception as e:
            logger.error(f"东方财富获取基金信息失败: {e}")
        return None

    @staticmethod
    def get_realtime_nav(fund_code: str) -> Optional[dict]:
        """
        获取基金实时估值/最新净值

        优先使用东方财富 fundgz 接口（含盘中估值），失败时降级到
        天天基金净值接口（只有历史净值，无实时估算）。

        Args:
            fund_code: 基金代码
        Returns:
            {"nav": 最新净值, "est_nav": 估算净值, "est_change_pct": 估算涨幅, ...}
            失败时返回 None
        """
        # ── 主接口：盘中估值 (jsonpgz wrapper) ───────────────────────────
        try:
            url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            raw = resp.text.strip()

            if "jsonpgz" in raw:
                # 去掉 JSONP 包装: jsonpgz({...});
                json_str = raw
                if json_str.startswith("jsonpgz("):
                    json_str = json_str[len("jsonpgz("):]
                if json_str.endswith(");"):
                    json_str = json_str[:-2]
                elif json_str.endswith(")"):
                    json_str = json_str[:-1]

                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError as je:
                    logger.warning(
                        f"fundgz JSON 解析失败 {fund_code}: {je} | raw={raw[:200]!r}"
                    )
                    data = None

                if data:
                    return {
                        "code": data.get("fundcode", fund_code),
                        "name": data.get("name", ""),
                        "nav": float(data.get("dwjz") or 0),
                        "est_nav": float(data.get("gsz") or 0),
                        "est_change_pct": float(data.get("gszzl") or 0),
                        "nav_date": data.get("jzrq", ""),
                        "est_time": data.get("gztime", ""),
                    }
            else:
                logger.debug(
                    f"fundgz 返回非 jsonpgz 格式 {fund_code}, raw={raw[:200]!r}"
                )

        except requests.RequestException as e:
            logger.warning(f"fundgz 请求失败 {fund_code}: {e}")
        except Exception as e:
            logger.warning(f"fundgz 处理异常 {fund_code}: {e}")

        # ── 降级接口：天天基金净值 API ────────────────────────────────────
        return FundDataFetcher._get_nav_fallback(fund_code)

    @staticmethod
    def _get_nav_fallback(fund_code: str) -> Optional[dict]:
        """
        降级：使用天天基金净值 API 获取最新确定净值（无实时估算）

        接口: https://api.fund.eastmoney.com/f10/lsjz
        """
        try:
            url = "https://api.fund.eastmoney.com/f10/lsjz"
            params = {
                "fundCode": fund_code,
                "pageIndex": 1,
                "pageSize": 1,
                "callback": "",
            }
            headers = {
                **HEADERS,
                "Referer": f"https://fundf10.eastmoney.com/jjjz_{fund_code}.html",
            }
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()

            # 若接口返回 JSONP 包装则去掉
            raw = resp.text.strip()
            if raw.startswith("jQuery") or raw.startswith("jsonp"):
                # jQuery12345({...})
                start = raw.index("(") + 1
                end = raw.rindex(")")
                raw = raw[start:end]

            data = json.loads(raw)
            records = (
                data.get("Data", {}).get("LSJZList") or []
            )
            if records:
                rec = records[0]
                nav = float(rec.get("DWJZ") or 0)
                nav_date = rec.get("FSRQ", "")
                logger.info(
                    f"降级接口获取净值成功 {fund_code}: nav={nav}, date={nav_date}"
                )
                return {
                    "code": fund_code,
                    "name": "",
                    "nav": nav,
                    "est_nav": nav,        # 降级时无估值，用确定净值代替
                    "est_change_pct": 0.0,
                    "nav_date": nav_date,
                    "est_time": "",
                }
        except json.JSONDecodeError as je:
            logger.error(
                f"降级接口 JSON 解析失败 {fund_code}: {je}"
            )
        except Exception as e:
            logger.error(f"降级接口请求失败 {fund_code}: {e}")

        return None

    @staticmethod
    def get_etf_realtime_price(etf_code: str) -> Optional[dict]:
        """
        获取 ETF 实时价格（场内交易价格）

        使用新浪财经接口

        Args:
            etf_code: ETF 代码如 "159941"
        Returns:
            {"price": 最新价, "change_pct": 涨跌幅, ...}
        """
        try:
            # 判断沪/深
            if etf_code.startswith(("51", "56", "58", "50")):
                sina_code = f"sh{etf_code}"
            else:
                sina_code = f"sz{etf_code}"

            url = f"https://hq.sinajs.cn/list={sina_code}"
            resp = requests.get(url, headers={
                **HEADERS,
                "Referer": "https://finance.sina.com.cn/",
            }, timeout=10)

            if resp.status_code == 200:
                text = resp.text.strip()
                if '="' in text:
                    data_str = text.split('="')[1].rstrip('";')
                    fields = data_str.split(",")
                    if len(fields) >= 32:
                        return {
                            "code": etf_code,
                            "name": fields[0],
                            "open": float(fields[1] or 0),
                            "prev_close": float(fields[2] or 0),
                            "price": float(fields[3] or 0),
                            "high": float(fields[4] or 0),
                            "low": float(fields[5] or 0),
                            "volume": float(fields[8] or 0),
                            "amount": float(fields[9] or 0),
                            "date": fields[30],
                            "time": fields[31],
                        }
        except Exception as e:
            logger.error(f"获取 ETF 实时价格失败 {etf_code}: {e}")
        return None

    @staticmethod
    def get_fund_nav_history(
        fund_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        获取基金历史净值（场外基金）

        Args:
            fund_code: 基金代码
            start_date: 起始日期 "YYYY-MM-DD"
            end_date: 结束日期 "YYYY-MM-DD"
        Returns:
            DataFrame with columns: trade_date, nav, acc_nav
        """
        try:
            import akshare as ak
            df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
            if df is not None and len(df) > 0:
                df = df.rename(columns={
                    "净值日期": "trade_date",
                    "单位净值": "nav",
                    "日增长率": "change_pct",
                })
                df["trade_date"] = pd.to_datetime(df["trade_date"])
                df["nav"] = pd.to_numeric(df["nav"], errors="coerce")

                if start_date:
                    df = df[df["trade_date"] >= pd.to_datetime(start_date)]
                if end_date:
                    df = df[df["trade_date"] <= pd.to_datetime(end_date)]

                return df.sort_values("trade_date").reset_index(drop=True)
        except Exception as e:
            logger.error(f"获取基金历史净值失败 {fund_code}: {e}")

        return pd.DataFrame()

    @staticmethod
    def get_etf_history(
        etf_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        获取 ETF 历史行情（场内 OHLCV）

        Args:
            etf_code: ETF 代码
            start_date: 起始日期 "YYYYMMDD"
            end_date: 结束日期 "YYYYMMDD"
        Returns:
            DataFrame with columns: trade_date, open, high, low, close, volume
        """
        try:
            import akshare as ak
            if not start_date:
                start_date = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
            if not end_date:
                end_date = datetime.now().strftime("%Y%m%d")

            df = ak.fund_etf_hist_em(
                symbol=etf_code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            )

            if df is not None and len(df) > 0:
                df = df.rename(columns={
                    "日期": "trade_date",
                    "开盘": "open",
                    "收盘": "close",
                    "最高": "high",
                    "最低": "low",
                    "成交量": "volume",
                })
                df["trade_date"] = pd.to_datetime(df["trade_date"])
                return df[["trade_date", "open", "high", "low", "close", "volume"]].sort_values("trade_date").reset_index(drop=True)

        except Exception as e:
            logger.error(f"获取 ETF 历史行情失败 {etf_code}: {e}")

        return pd.DataFrame()

    @staticmethod
    def fetch_and_update_price(instrument_id: int) -> Optional[dict]:
        """
        抓取最新价格并更新到数据库

        加入今日盈亏(today_pnl)和报价日期(price_date)的计算。
        """
        from app.extensions import db
        from app.models.instrument import Instrument
        from app.models.market_data import MarketData
        from app.models.position import Position

        instrument = db.session.get(Instrument, instrument_id)
        if not instrument:
            return None

        symbol = instrument.symbol
        result = None

        if instrument.trade_mode == "exchange_traded":
            # 场内 ETF/LOF - 拿实时价格
            data = FundDataFetcher.get_etf_realtime_price(symbol)
            if data and data.get("price", 0) > 0:
                result = {
                    "source": "sina_etf",
                    "price": data["price"],
                    "prev_close": data.get("prev_close", 0),
                    "name": data.get("name", ""),
                    "date": data.get("date", str(date.today())),
                }
        else:
            # 场外基金 - 拿净值与估算涨跌
            data = FundDataFetcher.get_realtime_nav(symbol)
            if data and data.get("nav", 0) > 0:
                result = {
                    "source": "eastmoney_nav",
                    "price": data["nav"],
                    "est_nav": data.get("est_nav", 0),
                    "change_pct": data.get("est_change_pct", 0),
                    "name": data.get("name", ""),
                    "date": data.get("nav_date", str(date.today())),
                    "est_time": data.get("est_time", ""),
                }

        if result:
            price = result["price"]
            price_date = result["date"]
            
            # 判断如果是场外基金，优先把当前界面需要反映的市场价设为估值（如果在盘中）
            # 或者干脆保留净值，并在记录上附加今日涨跌计算
            # 为了一致性：以 price = 最新确定净值 为准
            
            # 更新持仓的市场价格与今日盈亏
            positions = Position.query.filter_by(
                instrument_id=instrument_id,
                position_status="open",
            ).all()
            
            for pos in positions:
                pos.market_price = price
                pos.price_date = price_date
                
                # 计算今日盈亏
                if instrument.trade_mode == "exchange_traded":
                    prev_close = result.get("prev_close", price)
                    if prev_close > 0:
                        pos.today_pnl = pos.quantity * (price - prev_close)
                else:
                    # 场外基金：直接用 确定净值 * 估算涨跌幅% 计算今日盈亏估算值
                    change_pct = result.get("change_pct", 0)
                    pos.today_pnl = pos.quantity * price * (change_pct / 100.0)

                pos.update_market_value()

            db.session.commit()

            from app.services.position_service import PositionService
            PositionService.recalculate_weights()
            db.session.commit()

            logger.info(f"更新价格: {symbol} = {price} ({result['source']})")

        return result

    @staticmethod
    def fetch_all_prices() -> dict:
        """
        批量抓取所有活跃产品的最新价格

        Returns:
            {"updated": 更新数, "failed": 失败数, "details": [...]}
        """
        from app.models.instrument import Instrument
        from app.utils.constants import InstrumentStatus

        instruments = Instrument.query.filter(
            Instrument.status.in_([InstrumentStatus.ACTIVE.value, InstrumentStatus.WATCHLIST.value])
        ).all()

        summary = {"updated": 0, "failed": 0, "details": []}

        for inst in instruments:
            if inst.instrument_type == "cash":
                continue

            result = FundDataFetcher.fetch_and_update_price(inst.id)
            if result:
                summary["updated"] += 1
                summary["details"].append({
                    "symbol": inst.symbol,
                    "name": inst.name,
                    "price": result["price"],
                    "source": result["source"],
                })
            else:
                summary["failed"] += 1
                summary["details"].append({
                    "symbol": inst.symbol,
                    "name": inst.name,
                    "error": "获取价格失败",
                })

        return summary

    @staticmethod
    def fetch_and_import_history(instrument_id: int, days: int = 365) -> dict:
        """
        抓取历史数据并写入 market_data 表

        Args:
            instrument_id: 产品 ID
            days: 获取最近多少天的数据
        Returns:
            导入结果
        """
        from app.extensions import db
        from app.models.instrument import Instrument
        from app.models.market_data import MarketData
        from app.services.market_data_service import MarketDataService

        instrument = db.session.get(Instrument, instrument_id)
        if not instrument:
            return {"error": "产品不存在"}

        symbol = instrument.symbol
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end = datetime.now().strftime("%Y%m%d")

        imported = 0
        skipped = 0

        if instrument.trade_mode == "exchange_traded":
            df = FundDataFetcher.get_etf_history(symbol, start, end)
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    td = row["trade_date"].date() if hasattr(row["trade_date"], "date") else row["trade_date"]
                    existing = MarketData.query.filter_by(
                        instrument_id=instrument_id, trade_date=td
                    ).first()
                    if existing:
                        skipped += 1
                        continue

                    md = MarketData(
                        instrument_id=instrument_id,
                        trade_date=td,
                        open=float(row.get("open", 0)),
                        high=float(row.get("high", 0)),
                        low=float(row.get("low", 0)),
                        close=float(row.get("close", 0)),
                        volume=float(row.get("volume", 0)),
                    )
                    db.session.add(md)
                    imported += 1
        else:
            df = FundDataFetcher.get_fund_nav_history(
                symbol,
                start_date=(datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
                end_date=datetime.now().strftime("%Y-%m-%d"),
            )
            if df is not None and len(df) > 0:
                for _, row in df.iterrows():
                    td = row["trade_date"].date() if hasattr(row["trade_date"], "date") else row["trade_date"]
                    existing = MarketData.query.filter_by(
                        instrument_id=instrument_id, trade_date=td
                    ).first()
                    if existing:
                        skipped += 1
                        continue

                    md = MarketData(
                        instrument_id=instrument_id,
                        trade_date=td,
                        nav=float(row.get("nav", 0)),
                        close=float(row.get("nav", 0)),  # 用净值填充 close 字段
                    )
                    db.session.add(md)
                    imported += 1

        db.session.commit()

        # 计算技术指标
        if imported > 0:
            MarketDataService.calculate_indicators(instrument_id)

        result = {
            "symbol": symbol,
            "imported": imported,
            "skipped": skipped,
        }
        logger.info(f"历史数据导入: {result}")
        return result
