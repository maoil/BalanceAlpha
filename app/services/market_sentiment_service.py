"""
市场热度与恐慌指数服务
"""
from __future__ import annotations

import copy
import logging
import math
import re
import time
from datetime import datetime, timedelta
from statistics import mean
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class MarketSentimentService:
    """聚合市场热度、VIX 和人气榜信息。"""

    REQUEST_TIMEOUT = 15
    CACHE_TTL_SECONDS = 300
    HOT_LIST_LIMIT = 10
    VIX_SECID = "167.VIX"
    HOT_RANK_URL = "https://emappdata.eastmoney.com/stockrank/getAllCurrentList"
    HOT_UP_URL = "https://emappdata.eastmoney.com/stockrank/getAllHisRcList"
    VIX_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
    VIX_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    SINA_INDEX_URL = "https://hq.sinajs.cn/list="
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://quote.eastmoney.com/",
    }
    A_SHARE_INDEX_SYMBOLS = [
        {"symbol": "s_sh000001", "code": "000001", "name": "上证指数"},
        {"symbol": "s_sz399001", "code": "399001", "name": "深证成指"},
        {"symbol": "s_sz399006", "code": "399006", "name": "创业板指"},
        {"symbol": "s_sh000300", "code": "000300", "name": "沪深300"},
    ]

    _cache_snapshot: Optional[dict] = None
    _cache_expires_at: Optional[datetime] = None

    @classmethod
    def get_dashboard_snapshot(cls, force_refresh: bool = False) -> dict:
        """获取首页需要的市场情绪快照。"""
        now = datetime.now()
        if (
            not force_refresh
            and cls._cache_snapshot is not None
            and cls._cache_expires_at is not None
            and now < cls._cache_expires_at
        ):
            return copy.deepcopy(cls._cache_snapshot)

        snapshot = cls._fetch_dashboard_snapshot()
        cls._cache_snapshot = snapshot
        cls._cache_expires_at = now + timedelta(seconds=cls.CACHE_TTL_SECONDS)
        return copy.deepcopy(snapshot)

    @classmethod
    def _fetch_dashboard_snapshot(cls) -> dict:
        snapshot = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "heat": None,
            "vix": None,
            "indices": [],
            "hot_rank": [],
            "hot_up": [],
            "formula_note": "热度评分为自定义观察指标，综合A股指数、人气榜与VIX估算。",
            "errors": [],
        }

        with cls._create_session() as session:
            try:
                snapshot["vix"] = cls._get_vix_snapshot(session)
            except Exception as exc:
                logger.warning("获取 VIX 失败: %s", exc)
                snapshot["errors"].append("VIX 获取失败")

            try:
                snapshot["indices"] = cls._get_a_share_index_snapshot(session)
            except Exception as exc:
                logger.warning("获取 A 股指数快照失败: %s", exc)
                snapshot["errors"].append("A股指数获取失败")

            try:
                snapshot["hot_rank"] = cls._get_hot_rank(session, cls.HOT_RANK_URL, cls.HOT_LIST_LIMIT)
            except Exception as exc:
                logger.warning("获取人气榜失败: %s", exc)
                snapshot["errors"].append("人气榜获取失败")

            try:
                snapshot["hot_up"] = cls._get_hot_rank(session, cls.HOT_UP_URL, cls.HOT_LIST_LIMIT)
            except Exception as exc:
                logger.warning("获取飙升榜失败: %s", exc)
                snapshot["errors"].append("飙升榜获取失败")

        snapshot["heat"] = cls._build_market_heat(
            indices=snapshot["indices"],
            hot_rank=snapshot["hot_rank"],
            hot_up=snapshot["hot_up"],
            vix=snapshot["vix"],
        )
        return snapshot

    @classmethod
    def _create_session(cls) -> requests.Session:
        session = requests.Session()
        session.trust_env = False
        session.headers.update(cls.HEADERS)
        return session

    @staticmethod
    def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
        return max(lower, min(upper, value))

    @staticmethod
    def _safe_float(value: object, scale: float = 1.0) -> Optional[float]:
        if value in (None, "", "-"):
            return None
        try:
            return float(value) / scale
        except (TypeError, ValueError):
            return None

    @classmethod
    def _get_json(cls, session: requests.Session, url: str, params: dict | None = None) -> dict:
        last_error = None
        for attempt in range(4):
            try:
                response = session.get(url, params=params, timeout=cls.REQUEST_TIMEOUT)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(0.35 * (attempt + 1))
        raise last_error

    @classmethod
    def _post_json(
        cls,
        session: requests.Session,
        url: str,
        payload: dict,
    ) -> dict:
        last_error = None
        for attempt in range(3):
            try:
                response = session.post(url, json=payload, timeout=cls.REQUEST_TIMEOUT)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.3 * (attempt + 1))
        raise last_error

    @classmethod
    def _get_vix_snapshot(cls, session: requests.Session) -> dict:
        last_error = None
        try:
            for attempt in range(2):
                try:
                    response = session.get(
                        cls.VIX_QUOTE_URL,
                        params={
                            "secid": cls.VIX_SECID,
                            "fields": "f57,f58,f43,f44,f45,f46,f60,f169,f170",
                        },
                        timeout=3,
                    )
                    response.raise_for_status()
                    data = response.json()
                    quote = data.get("data") or {}
                    if not quote:
                        raise ValueError("VIX 返回为空")

                    value = cls._safe_float(quote.get("f43"), 100)
                    change_pct = cls._safe_float(quote.get("f170"), 100)
                    change_amount = cls._safe_float(quote.get("f169"), 100)
                    level_label, badge_class, description = cls._classify_vix_level(value)

                    return {
                        "code": quote.get("f57", "VIX"),
                        "name": quote.get("f58", "VIX恐慌指数"),
                        "value": value,
                        "open": cls._safe_float(quote.get("f46"), 100),
                        "high": cls._safe_float(quote.get("f44"), 100),
                        "low": cls._safe_float(quote.get("f45"), 100),
                        "prev_close": cls._safe_float(quote.get("f60"), 100),
                        "change_amount": change_amount,
                        "change_pct": change_pct,
                        "level_label": level_label,
                        "badge_class": badge_class,
                        "description": description,
                    }
                except (requests.RequestException, ValueError) as exc:
                    last_error = exc
                    if attempt < 1:
                        time.sleep(0.25)
        finally:
            if last_error:
                logger.warning("东方财富 VIX 接口失败，回退 Cboe 页面: %s", last_error)
        try:
            return cls._get_vix_snapshot_from_cboe()
        except Exception:
            if last_error is not None:
                raise last_error
            raise

    @classmethod
    def get_vix_history(cls, days: int = 30, interval: str = "daily") -> dict:
        """Fetch VIX historical points for dashboard trend charts."""
        days = max(1, int(days or 30))
        interval = interval if interval in {"daily", "intraday"} else "daily"
        klt = "101" if interval == "daily" else "1"

        try:
            with cls._create_session() as session:
                data = cls._get_json(
                    session,
                    cls.VIX_KLINE_URL,
                    params={
                        "secid": cls.VIX_SECID,
                        "klt": klt,
                        "fqt": "1",
                        "lmt": days,
                        "end": "20500101",
                        "fields1": "f1,f2,f3,f4,f5,f6",
                        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                    },
                )
            klines = (data.get("data") or {}).get("klines") or []
            series = []
            for item in klines:
                fields = str(item).split(",")
                if len(fields) < 5:
                    continue
                close = cls._safe_float(fields[2])
                if close is None:
                    continue
                series.append(
                    {
                        "date": fields[0],
                        "open": cls._safe_float(fields[1]),
                        "close": close,
                        "value": close,
                        "high": cls._safe_float(fields[3]),
                        "low": cls._safe_float(fields[4]),
                        "change_pct": cls._safe_float(fields[8]) if len(fields) > 8 else None,
                    }
                )
            if series:
                return {
                    "series": series,
                    "range": f"{days}d",
                    "interval": interval,
                    "source": "eastmoney",
                }
        except Exception as exc:
            logger.warning("鑾峰彇 VIX 鍘嗗彶搴忓垪澶辫触: %s", exc)

        snapshot = cls.get_dashboard_snapshot().get("vix") or {}
        value = snapshot.get("value")
        series = []
        if value is not None:
            series.append(
                {
                    "date": datetime.now().date().isoformat(),
                    "open": snapshot.get("open"),
                    "close": value,
                    "value": value,
                    "high": snapshot.get("high"),
                    "low": snapshot.get("low"),
                    "change_pct": snapshot.get("change_pct"),
                }
            )
        return {
            "series": series,
            "range": f"{days}d",
            "interval": interval,
            "source": "snapshot_fallback",
        }

    @classmethod
    def _extract_cboe_metric(cls, html: str, label: str) -> Optional[float]:
        pattern = rf"{re.escape(label)}</span><span[^>]*>([-\d.]+)</span>"
        match = re.search(pattern, html)
        if match:
            return cls._safe_float(match.group(1))
        return None

    @classmethod
    def _get_vix_snapshot_from_cboe(cls) -> dict:
        with cls._create_session() as session:
            response = session.get("https://www.cboe.com/tradable_products/vix/", timeout=3)
            response.raise_for_status()
            html = response.text

        value_match = re.search(r"\$<!-- -->([-\d.]+)</h2><p[^>]*>VIX Spot Price", html)
        change_match = re.search(r">([-\d.]+)<!-- -->%<span[^>]*>\s*\(([-\d.]+)\)</span>", html)
        value = cls._safe_float(value_match.group(1)) if value_match else None
        change_pct = cls._safe_float(change_match.group(1)) if change_match else None
        change_amount = cls._safe_float(change_match.group(2)) if change_match else None

        if value is None:
            raise ValueError("Cboe 页面未解析到 VIX")

        level_label, badge_class, description = cls._classify_vix_level(value)
        return {
            "code": "VIX",
            "name": "VIX恐慌指数",
            "value": value,
            "open": cls._extract_cboe_metric(html, "Open"),
            "high": None,
            "low": None,
            "prev_close": cls._extract_cboe_metric(html, "Prev. Close"),
            "change_amount": change_amount,
            "change_pct": change_pct,
            "level_label": level_label,
            "badge_class": badge_class,
            "description": description,
        }

    @classmethod
    def _get_a_share_index_snapshot(cls, session: requests.Session) -> list[dict]:
        symbols = ",".join(item["symbol"] for item in cls.A_SHARE_INDEX_SYMBOLS)
        response = session.get(
            f"{cls.SINA_INDEX_URL}{symbols}",
            headers={"Referer": "https://finance.sina.com.cn/"},
            timeout=cls.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        raw_text = response.content.decode("gbk", errors="ignore")

        symbol_map = {item["symbol"]: item for item in cls.A_SHARE_INDEX_SYMBOLS}
        results = []
        for line in raw_text.splitlines():
            line = line.strip()
            if not line or '="' not in line:
                continue

            prefix, payload = line.split('="', 1)
            symbol = prefix.replace("var hq_str_", "")
            fields = payload.rstrip('";').split(",")
            if len(fields) < 6 or symbol not in symbol_map:
                continue

            meta = symbol_map[symbol]
            results.append(
                {
                    "symbol": symbol,
                    "code": meta["code"],
                    "name": fields[0] or meta["name"],
                    "latest": cls._safe_float(fields[1]),
                    "change_amount": cls._safe_float(fields[2]),
                    "change_pct": cls._safe_float(fields[3]),
                    "volume": cls._safe_float(fields[4]),
                    "amount": cls._safe_float(fields[5]),
                }
            )

        if not results:
            raise ValueError("A股指数快照为空")

        return results

    @classmethod
    def _get_sina_stock_quotes(
        cls,
        session: requests.Session,
        codes: list[str],
    ) -> dict[str, dict]:
        symbols = []
        for code in codes:
            if code.startswith("SZ"):
                symbols.append(f"sz{code[2:]}")
            elif code.startswith("SH"):
                symbols.append(f"sh{code[2:]}")

        if not symbols:
            return {}

        response = session.get(
            f"{cls.SINA_INDEX_URL}{','.join(symbols)}",
            headers={"Referer": "https://finance.sina.com.cn/"},
            timeout=cls.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        raw_text = response.content.decode("gbk", errors="ignore")

        quote_map = {}
        for line in raw_text.splitlines():
            line = line.strip()
            if not line or '="' not in line:
                continue

            prefix, payload = line.split('="', 1)
            symbol = prefix.replace("var hq_str_", "")
            fields = payload.rstrip('";').split(",")
            if len(fields) < 4:
                continue

            if symbol.startswith("sz"):
                code = f"SZ{symbol[2:]}"
            elif symbol.startswith("sh"):
                code = f"SH{symbol[2:]}"
            else:
                code = symbol.upper()

            prev_close = cls._safe_float(fields[2])
            latest_price = cls._safe_float(fields[3])
            change_pct = None
            if prev_close not in (None, 0) and latest_price is not None:
                change_pct = (latest_price / prev_close - 1) * 100

            quote_map[code] = {
                "name": fields[0] or code,
                "latest_price": latest_price,
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
            }

        return quote_map

    @classmethod
    def _get_hot_rank(
        cls,
        session: requests.Session,
        url: str,
        limit: int,
    ) -> list[dict]:
        payload = {
            "appId": "appId01",
            "globalId": "786e4c21-70dc-435a-93bb-38",
            "marketType": "",
            "pageNo": 1,
            "pageSize": limit,
        }
        rank_json = cls._post_json(session, url, payload)
        rank_items = rank_json.get("data") or []
        if not rank_items:
            return []

        quote_map = cls._get_sina_stock_quotes(
            session,
            [str(item.get("sc", "")) for item in rank_items],
        )

        results = []
        for item in rank_items:
            market_code = item.get("sc", "")
            plain_code = market_code[2:] if len(market_code) > 2 else market_code
            quote = quote_map.get(market_code, {})
            results.append(
                {
                    "code": market_code,
                    "plain_code": plain_code,
                    "name": quote.get("name", market_code),
                    "rank": int(item.get("rk") or 0),
                    "rank_change": cls._safe_float(item.get("hrc") or item.get("hisRc")),
                    "latest_price": quote.get("latest_price"),
                    "change_pct": quote.get("change_pct"),
                }
            )

        return results

    @classmethod
    def _classify_vix_level(cls, value: Optional[float]) -> tuple[str, str, str]:
        if value is None:
            return "未知", "bg-secondary", "暂无可用的 VIX 数据。"
        if value >= 35:
            return "极度恐慌", "bg-danger", "市场处于高波动区间，短线情绪明显紧张。"
        if value >= 25:
            return "高波动", "bg-warning text-dark", "风险偏好承压，宜控制追涨节奏。"
        if value >= 18:
            return "警戒", "bg-info text-dark", "情绪开始紧张，需留意外部风险放大。"
        if value >= 13:
            return "中性", "bg-primary", "情绪大体平稳，风险偏好没有明显失衡。"
        return "平静", "bg-success", "市场波动预期较低，但也要防范过度乐观。"

    @classmethod
    def _classify_heat_level(cls, score: Optional[int]) -> tuple[str, str]:
        if score is None:
            return "未知", "bg-secondary"
        if score >= 80:
            return "过热", "bg-danger"
        if score >= 65:
            return "偏热", "bg-warning text-dark"
        if score >= 45:
            return "中性", "bg-primary"
        if score >= 30:
            return "偏冷", "bg-info text-dark"
        return "冰点", "bg-secondary"

    @classmethod
    def _build_market_heat(
        cls,
        indices: list[dict],
        hot_rank: list[dict],
        hot_up: list[dict],
        vix: Optional[dict],
    ) -> dict:
        if not indices and not hot_rank and not vix:
            return {
                "score": None,
                "level_label": "未知",
                "badge_class": "bg-secondary",
                "summary": "暂无足够数据计算市场热度。",
                "index_score": None,
                "popularity_score": None,
                "risk_score": None,
                "avg_index_change_pct": None,
                "hot_up_ratio": None,
                "top_hot_avg_change_pct": None,
            }

        index_changes = [item["change_pct"] for item in indices if item.get("change_pct") is not None]
        avg_index_change = mean(index_changes) if index_changes else 0.0
        positive_indices = sum(1 for value in index_changes if value > 0)
        index_score = cls._clamp(50 + avg_index_change * 12 + (positive_indices - len(index_changes) / 2) * 6)

        hot_changes = [item["change_pct"] for item in hot_rank if item.get("change_pct") is not None]
        hot_avg_change = mean(hot_changes) if hot_changes else 0.0
        hot_up_ratio = (
            sum(1 for value in hot_changes if value > 0) / len(hot_changes)
            if hot_changes else 0.0
        )
        rank_jumps = [max(item.get("rank_change") or 0, 0) for item in hot_up]
        avg_rank_jump = mean(rank_jumps) if rank_jumps else 0.0
        popularity_score = cls._clamp(
            45
            + hot_avg_change * 6
            + hot_up_ratio * 25
            + min(math.log1p(avg_rank_jump) * 4, 18)
        )

        vix_value = (vix or {}).get("value")
        risk_score = 60.0
        if vix_value is not None:
            risk_score = cls._clamp(100 - max(vix_value - 12, 0) * 4)

        score = round(index_score * 0.35 + popularity_score * 0.45 + risk_score * 0.20)
        level_label, badge_class = cls._classify_heat_level(score)

        summary_parts = []
        if avg_index_change >= 1:
            summary_parts.append("核心指数整体偏强")
        elif avg_index_change <= -1:
            summary_parts.append("核心指数整体承压")
        else:
            summary_parts.append("核心指数偏震荡")

        if hot_up_ratio >= 0.7:
            summary_parts.append("人气股赚钱效应明显")
        elif hot_up_ratio <= 0.4:
            summary_parts.append("人气股跟涨意愿偏弱")
        else:
            summary_parts.append("人气股分化较大")

        if vix_value is not None:
            if vix_value >= 25:
                summary_parts.append("VIX抬升压制风险偏好")
            elif vix_value <= 15:
                summary_parts.append("VIX较低，外部恐慌有限")
            else:
                summary_parts.append("VIX处于常态警戒区间")

        return {
            "score": score,
            "level_label": level_label,
            "badge_class": badge_class,
            "summary": "，".join(summary_parts) + "。",
            "index_score": round(index_score, 1),
            "popularity_score": round(popularity_score, 1),
            "risk_score": round(risk_score, 1),
            "avg_index_change_pct": round(avg_index_change, 2),
            "hot_up_ratio": round(hot_up_ratio * 100, 1),
            "top_hot_avg_change_pct": round(hot_avg_change, 2),
        }
