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

from app.utils.helpers import to_float as _helpers_to_float, round_metric as _helpers_round_metric
from datetime import date, datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_DAYS = 365 * 5
INDICATOR_LOOKBACK_DAYS = 400

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
            logger.error("搜索基金失败: %s", e)
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
            logger.error("akshare 搜索基金失败: %s", e)
            return []

    @staticmethod
    def _get_basic_fund_info(fund_code: str) -> dict:
        """使用 akshare 拉取基金基础信息。"""
        try:
            import akshare as ak

            info_df = ak.fund_individual_basic_info_xq(symbol=fund_code)
            info = {}
            if info_df is not None and len(info_df) > 0:
                for _, row in info_df.iterrows():
                    key = str(row.iloc[0]).strip()
                    val = str(row.iloc[1]).strip()
                    if key:
                        info[key] = val
            return info
        except Exception as e:
            logger.warning("akshare 获取基金信息失败: %s", e)
            return {}

    @staticmethod
    def _infer_instrument_type(name: str = "", fund_type: str = "") -> str:
        """根据名称和基金类型推断产品类型。"""
        normalized = f"{name} {fund_type}".upper()
        if "联接" in (name or ""):
            return "fund"
        if "LOF" in normalized:
            return "lof"
        if "ETF" in normalized:
            return "etf"
        return "fund"

    @staticmethod
    def _infer_trade_mode(instrument_type: str) -> str:
        return "exchange_traded" if instrument_type in {"etf", "lof"} else "eod_nav"

    @staticmethod
    def _to_float(value: object) -> Optional[float]:
        """委托给 helpers.to_float"""
        return _helpers_to_float(value)

    @staticmethod
    def _round_metric(value: object, digits: int = 4) -> Optional[float]:
        """委托给 helpers.round_metric"""
        return _helpers_round_metric(value, digits)

    @staticmethod
    def _calc_period_return(prices: pd.Series, periods: int) -> Optional[float]:
        if len(prices) <= periods:
            return None

        latest_price = FundDataFetcher._to_float(prices.iloc[-1])
        base_price = FundDataFetcher._to_float(prices.iloc[-periods - 1])
        if latest_price is None or base_price is None or base_price <= 0:
            return None
        return (latest_price / base_price) - 1

    @staticmethod
    def _calc_price_distance(price: object, average: object) -> Optional[float]:
        latest_price = FundDataFetcher._to_float(price)
        average_price = FundDataFetcher._to_float(average)
        if latest_price is None or average_price is None or average_price <= 0:
            return None
        return (latest_price / average_price) - 1

    @staticmethod
    def _build_quote_snapshot(fund_code: str, trade_mode: str) -> dict:
        """统一聚合场内价格和场外净值快照。"""
        if trade_mode == "exchange_traded":
            etf_quote = FundDataFetcher.get_etf_realtime_price(fund_code)
            latest_price = FundDataFetcher._to_float((etf_quote or {}).get("price"))
            if latest_price is not None and latest_price > 0:
                prev_close = FundDataFetcher._to_float(etf_quote.get("prev_close"))
                change_pct = None
                if prev_close is not None and prev_close > 0:
                    change_pct = (latest_price / prev_close - 1) * 100

                return {
                    "source": "sina_etf",
                    "latest_price": FundDataFetcher._round_metric(latest_price),
                    "latest_nav": None,
                    "estimated_nav": None,
                    "prev_close": FundDataFetcher._round_metric(prev_close),
                    "change_pct": FundDataFetcher._round_metric(change_pct, 2),
                    "quote_date": etf_quote.get("date", ""),
                    "quote_time": etf_quote.get("time", ""),
                }

        nav_quote = FundDataFetcher.get_realtime_nav(fund_code)
        nav = FundDataFetcher._to_float((nav_quote or {}).get("nav"))
        if nav is None or nav <= 0:
            return {}

        est_nav = FundDataFetcher._to_float(nav_quote.get("est_nav"))
        change_pct = FundDataFetcher._to_float(nav_quote.get("est_change_pct"))
        latest_price = est_nav if est_nav is not None and est_nav > 0 else nav

        return {
            "source": "eastmoney_nav",
            "latest_price": FundDataFetcher._round_metric(latest_price),
            "latest_nav": FundDataFetcher._round_metric(nav),
            "estimated_nav": FundDataFetcher._round_metric(est_nav),
            "prev_close": None,
            "change_pct": FundDataFetcher._round_metric(change_pct, 2),
            "quote_date": nav_quote.get("nav_date", ""),
            "quote_time": nav_quote.get("est_time", ""),
        }

    @staticmethod
    def _get_indicator_history(fund_code: str, trade_mode: str) -> tuple[pd.DataFrame, str]:
        """获取计算指标所需的近期历史数据。"""
        start = datetime.now() - timedelta(days=INDICATOR_LOOKBACK_DAYS)
        end = datetime.now()

        if trade_mode == "exchange_traded":
            history_df = FundDataFetcher.get_etf_history(
                fund_code,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
            if history_df is not None and not history_df.empty:
                return history_df, "etf_history"

        history_df = FundDataFetcher.get_fund_nav_history(
            fund_code,
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
        )
        if history_df is not None and not history_df.empty:
            return history_df, "fund_nav_history"

        return pd.DataFrame(), ""

    @staticmethod
    def _build_history_indicators(history_df: pd.DataFrame) -> dict:
        """从历史价格/净值序列生成多种指标。"""
        if history_df is None or history_df.empty:
            return {}

        price_column = None
        if "close" in history_df.columns and history_df["close"].notna().any():
            price_column = "close"
        elif "nav" in history_df.columns and history_df["nav"].notna().any():
            price_column = "nav"
        if not price_column:
            return {}

        df = history_df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df[price_column] = pd.to_numeric(df[price_column], errors="coerce")
        df = df.dropna(subset=[price_column]).sort_values("trade_date").reset_index(drop=True)
        if df.empty:
            return {}

        prices = df[price_column]
        latest_price = prices.iloc[-1]
        ma20 = prices.tail(20).mean() if len(prices) >= 20 else None
        ma60 = prices.tail(60).mean() if len(prices) >= 60 else None
        ma120 = prices.tail(120).mean() if len(prices) >= 120 else None

        recent_high_60d = prices.tail(60).max() if len(prices) >= 2 else None
        drawdown_60d = None
        if recent_high_60d is not None and recent_high_60d > 0:
            drawdown_60d = (latest_price / recent_high_60d) - 1

        latest_trade_date = df["trade_date"].iloc[-1]
        if hasattr(latest_trade_date, "date"):
            latest_trade_date = latest_trade_date.date().isoformat()
        else:
            latest_trade_date = str(latest_trade_date)

        return {
            "latest_trade_date": latest_trade_date,
            "data_points": int(len(df)),
            "ma20": FundDataFetcher._round_metric(ma20),
            "ma60": FundDataFetcher._round_metric(ma60),
            "ma120": FundDataFetcher._round_metric(ma120),
            "price_vs_ma20": FundDataFetcher._round_metric(
                FundDataFetcher._calc_price_distance(latest_price, ma20)
            ),
            "price_vs_ma60": FundDataFetcher._round_metric(
                FundDataFetcher._calc_price_distance(latest_price, ma60)
            ),
            "price_vs_ma120": FundDataFetcher._round_metric(
                FundDataFetcher._calc_price_distance(latest_price, ma120)
            ),
            "drawdown_60d": FundDataFetcher._round_metric(drawdown_60d),
            "relative_strength_20d": FundDataFetcher._round_metric(
                FundDataFetcher._calc_period_return(prices, 20)
            ),
            "return_1m": FundDataFetcher._round_metric(FundDataFetcher._calc_period_return(prices, 20)),
            "return_3m": FundDataFetcher._round_metric(FundDataFetcher._calc_period_return(prices, 60)),
            "return_6m": FundDataFetcher._round_metric(FundDataFetcher._calc_period_return(prices, 120)),
            "return_1y": FundDataFetcher._round_metric(FundDataFetcher._calc_period_return(prices, 250)),
        }

    @staticmethod
    def _get_history_indicators(fund_code: str, trade_mode: str) -> dict:
        history_df, source = FundDataFetcher._get_indicator_history(fund_code, trade_mode)
        indicators = FundDataFetcher._build_history_indicators(history_df)
        if indicators:
            indicators["source"] = source
        return indicators

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
            info = FundDataFetcher._get_basic_fund_info(fund_code)
            fallback_info = {}
            if not info:
                fallback_info = FundDataFetcher._get_fund_info_em(fund_code) or {}

            name = (
                info.get("基金全称")
                or info.get("基金简称")
                or fallback_info.get("name")
                or fund_code
            )
            short_name = info.get("基金简称") or fallback_info.get("short_name") or ""
            fund_type = info.get("基金类型") or fallback_info.get("type") or ""
            instrument_type = FundDataFetcher._infer_instrument_type(short_name or name, fund_type)
            trade_mode = FundDataFetcher._infer_trade_mode(instrument_type)
            quote = FundDataFetcher._build_quote_snapshot(fund_code, trade_mode)
            indicators = FundDataFetcher._get_history_indicators(fund_code, trade_mode)

            return {
                "code": fund_code,
                "name": name,
                "short_name": short_name,
                "type": fund_type,
                "instrument_type": instrument_type,
                "trade_mode": trade_mode,
                "manager": info.get("基金经理", ""),
                "company": info.get("基金公司", info.get("管理人", "")),
                "inception_date": info.get("成立日期", ""),
                "benchmark": info.get("业绩比较基准", ""),
                "latest_price": quote.get("latest_price"),
                "nav": quote.get("latest_nav"),
                "est_nav": quote.get("estimated_nav"),
                "change_pct": quote.get("change_pct"),
                "est_change_pct": quote.get("change_pct"),
                "quote_date": quote.get("quote_date", ""),
                "quote_time": quote.get("quote_time", ""),
                "nav_date": quote.get("quote_date", ""),
                "quote": quote,
                "indicators": indicators,
                "raw_info": info,
            }
        except Exception as e:
            logger.warning("获取基金信息失败: %s，使用备选方案", e)
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
            logger.error("东方财富获取基金信息失败: %s", e)
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
            logger.warning("fundgz 请求失败 %s: %s", fund_code, e)
        except Exception as e:
            logger.warning("fundgz 处理异常 %s: %s", fund_code, e)

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
            logger.error("降级接口请求失败 %s: %s", fund_code, e)

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
            logger.error("获取 ETF 实时价格失败 %s: %s", etf_code, e)
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
            logger.error("获取基金历史净值失败 %s: %s", fund_code, e)

        return pd.DataFrame()

    @staticmethod
    def _normalize_history_frame(df: pd.DataFrame, numeric_columns: list[str]) -> pd.DataFrame:
        """Normalize date and numeric columns in a history DataFrame."""
        normalized = df.copy()
        if "trade_date" in normalized.columns:
            normalized["trade_date"] = pd.to_datetime(normalized["trade_date"])

        for column in numeric_columns:
            if column not in normalized.columns:
                continue
            series = normalized[column]
            if series.dtype == object:
                series = series.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False)
            normalized[column] = pd.to_numeric(series, errors="coerce")

        return normalized

    @staticmethod
    def get_fund_nav_history_extended(
        fund_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Get fund nav history with acc_nav for daily imports."""
        try:
            import akshare as ak

            df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
            if df is None or df.empty:
                return pd.DataFrame()

            df = df.rename(columns={
                "净值日期": "trade_date",
                "单位净值": "nav",
                "累计净值": "acc_nav",
                "日增长率": "change_pct",
            })
            df = FundDataFetcher._normalize_history_frame(
                df,
                numeric_columns=["nav", "acc_nav", "change_pct"],
            )

            if start_date:
                df = df[df["trade_date"] >= pd.to_datetime(start_date)]
            if end_date:
                df = df[df["trade_date"] <= pd.to_datetime(end_date)]

            keep_columns = [
                column for column in ("trade_date", "nav", "acc_nav", "change_pct")
                if column in df.columns
            ]
            return df[keep_columns].sort_values("trade_date").reset_index(drop=True)
        except Exception as e:
            logger.error("获取基金历史净值失败 %s: %s", fund_code, e)
            return pd.DataFrame()

    @staticmethod
    def get_exchange_traded_history_extended(
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Get exchange-traded history with amount/turnover/amplitude/nav."""
        try:
            import akshare as ak

            if not start_date:
                start_date = (datetime.now() - timedelta(days=DEFAULT_HISTORY_DAYS)).strftime("%Y%m%d")
            if not end_date:
                end_date = datetime.now().strftime("%Y%m%d")

            price_df = ak.fund_etf_hist_em(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            )
            if price_df is None or price_df.empty:
                return pd.DataFrame()

            price_df = price_df.rename(columns={
                "日期": "trade_date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "振幅": "amplitude",
                "换手率": "turnover_rate",
            })
            price_df = FundDataFetcher._normalize_history_frame(
                price_df,
                numeric_columns=[
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "amount",
                    "amplitude",
                    "turnover_rate",
                ],
            )
            price_df = price_df.sort_values("trade_date").reset_index(drop=True)
            price_df["prev_close"] = price_df["close"].shift(1)

            nav_df = FundDataFetcher.get_fund_nav_history_extended(
                symbol,
                start_date=datetime.strptime(start_date, "%Y%m%d").strftime("%Y-%m-%d"),
                end_date=datetime.strptime(end_date, "%Y%m%d").strftime("%Y-%m-%d"),
            )
            if nav_df is not None and not nav_df.empty:
                nav_columns = [
                    column for column in ("trade_date", "nav", "acc_nav")
                    if column in nav_df.columns
                ]
                price_df = price_df.merge(nav_df[nav_columns], on="trade_date", how="left")

            keep_columns = [
                column for column in (
                    "trade_date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "prev_close",
                    "volume",
                    "amount",
                    "amplitude",
                    "turnover_rate",
                    "nav",
                    "acc_nav",
                )
                if column in price_df.columns
            ]
            return price_df[keep_columns].sort_values("trade_date").reset_index(drop=True)
        except Exception as e:
            logger.error("获取场内历史行情失败 %s: %s", symbol, e)
            return pd.DataFrame()

    @staticmethod
    def _build_market_data_payload(row: pd.Series, trade_mode: str) -> dict:
        """Map one imported history row to MarketData raw fields."""
        payload = {
            "open": FundDataFetcher._to_float(row.get("open")),
            "high": FundDataFetcher._to_float(row.get("high")),
            "low": FundDataFetcher._to_float(row.get("low")),
            "close": FundDataFetcher._to_float(row.get("close")),
            "prev_close": FundDataFetcher._to_float(row.get("prev_close")),
            "volume": FundDataFetcher._to_float(row.get("volume")),
            "amount": FundDataFetcher._to_float(row.get("amount")),
            "turnover_rate": FundDataFetcher._to_float(row.get("turnover_rate")),
            "amplitude": FundDataFetcher._to_float(row.get("amplitude")),
            "nav": FundDataFetcher._to_float(row.get("nav")),
            "acc_nav": FundDataFetcher._to_float(row.get("acc_nav")),
            "est_nav": FundDataFetcher._to_float(row.get("est_nav")),
            "iopv": FundDataFetcher._to_float(row.get("iopv")),
        }
        if trade_mode != "exchange_traded" and payload["close"] is None:
            payload["close"] = payload["nav"]
        return payload

    @staticmethod
    def _upsert_market_data(market_data, payload: dict) -> bool:
        """Update non-null fields on an existing MarketData row."""
        changed = False
        for field, value in payload.items():
            if value is None:
                continue
            if getattr(market_data, field) != value:
                setattr(market_data, field, value)
                changed = True
        return changed

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
                start_date = (datetime.now() - timedelta(days=DEFAULT_HISTORY_DAYS)).strftime("%Y%m%d")
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
            logger.error("获取 ETF 历史行情失败 %s: %s", etf_code, e)

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

            logger.info("更新价格: %s = %s (%s)", symbol, price, result['source'])

        return result

    @staticmethod
    def _fetch_and_import_history_v1(instrument_id: int, days: int = DEFAULT_HISTORY_DAYS) -> dict:
        """Fetch history and import or enrich market_data rows."""
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
        start_nav = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        end_nav = datetime.now().strftime("%Y-%m-%d")

        imported = 0
        updated = 0
        skipped = 0

        if instrument.trade_mode == "exchange_traded":
            df = FundDataFetcher.get_exchange_traded_history_extended(symbol, start, end)
        else:
            df = FundDataFetcher.get_fund_nav_history_extended(
                symbol,
                start_date=start_nav,
                end_date=end_nav,
            )

        if df is not None and len(df) > 0:
            for _, row in df.iterrows():
                trade_date_value = row["trade_date"].date() if hasattr(row["trade_date"], "date") else row["trade_date"]
                payload = FundDataFetcher._build_market_data_payload(row, instrument.trade_mode)
                existing = MarketData.query.filter_by(
                    instrument_id=instrument_id,
                    trade_date=trade_date_value,
                ).first()

                if existing:
                    changed = FundDataFetcher._upsert_market_data(existing, payload)
                    if changed:
                        updated += 1
                    else:
                        skipped += 1
                    continue

                market_data = MarketData(
                    instrument_id=instrument_id,
                    trade_date=trade_date_value,
                    **payload,
                )
                db.session.add(market_data)
                imported += 1

        db.session.commit()

        if imported > 0 or updated > 0:
            MarketDataService.calculate_indicators(instrument_id)

        result = {
            "symbol": symbol,
            "days_requested": days,
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
        }
        logger.info("历史数据导入: %s", result)
        return result

    @staticmethod
    def fetch_all_prices() -> dict:
        """
        批量抓取所有活跃产品的最新价格

        Returns:
            {"updated": 更新数, "failed": 失败数, "details": [...]}
        """
        from app.models.instrument import Instrument
        from app.services.dca_order_service import DcaOrderService
        from app.services.dca_plan_service import DcaPlanService
        from app.utils.constants import InstrumentStatus

        instruments = Instrument.query.filter(
            Instrument.status.in_([InstrumentStatus.ACTIVE.value, InstrumentStatus.WATCHLIST.value])
        ).all()

        summary = {
            "updated": 0,
            "failed": 0,
            "details": [],
            "dca_created": 0,
            "dca_confirmed": 0,
        }

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

        dca_generation = DcaPlanService.generate_due_orders(run_date=date.today())
        dca_confirmation = DcaOrderService.confirm_pending_orders(run_date=date.today())
        summary["dca_created"] = dca_generation.get("created", 0)
        summary["dca_confirmed"] = dca_confirmation.get("confirmed", 0)

        return summary

    @staticmethod
    def _fetch_and_import_history_legacy(instrument_id: int, days: int = DEFAULT_HISTORY_DAYS) -> dict:
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
            "days_requested": days,
            "imported": imported,
            "skipped": skipped,
        }
        logger.info("历史数据导入: %s", result)
        return result
    @staticmethod
    def fetch_and_import_history(instrument_id: int, days: int = DEFAULT_HISTORY_DAYS) -> dict:
        """Fetch history and import or enrich market_data rows."""
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
        start_nav = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        end_nav = datetime.now().strftime("%Y-%m-%d")

        imported = 0
        updated = 0
        skipped = 0

        if instrument.trade_mode == "exchange_traded":
            df = FundDataFetcher.get_exchange_traded_history_extended(symbol, start, end)
        else:
            df = FundDataFetcher.get_fund_nav_history_extended(
                symbol,
                start_date=start_nav,
                end_date=end_nav,
            )

        if df is not None and len(df) > 0:
            for _, row in df.iterrows():
                trade_date_value = row["trade_date"].date() if hasattr(row["trade_date"], "date") else row["trade_date"]
                payload = FundDataFetcher._build_market_data_payload(row, instrument.trade_mode)
                existing = MarketData.query.filter_by(
                    instrument_id=instrument_id,
                    trade_date=trade_date_value,
                ).first()

                if existing:
                    changed = FundDataFetcher._upsert_market_data(existing, payload)
                    if changed:
                        updated += 1
                    else:
                        skipped += 1
                    continue

                market_data = MarketData(
                    instrument_id=instrument_id,
                    trade_date=trade_date_value,
                    **payload,
                )
                db.session.add(market_data)
                imported += 1

        db.session.commit()

        if imported > 0 or updated > 0:
            MarketDataService.calculate_indicators(instrument_id)

        result = {
            "symbol": symbol,
            "days_requested": days,
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
        }
        logger.info("历史数据导入: %s", result)
        return result
