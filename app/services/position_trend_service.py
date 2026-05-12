import logging
from typing import Optional

import requests

from app.models.position import Position
from app.utils.constants import TradeMode
from app.utils.helpers import round_metric, to_float

logger = logging.getLogger(__name__)


class PositionTrendService:
    SINA_INTRADAY_URL = (
        "https://quotes.sina.cn/cn/api/json_v2.php/"
        "CN_MarketDataService.getKLineData"
    )
    SINA_QUOTE_URL = "https://hq.sinajs.cn/list="
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://finance.sina.com.cn/",
    }

    @staticmethod
    def build_for_position(
        position: Position,
    ) -> Optional[dict]:
        resolved = PositionTrendService._resolve_source_symbol(position)
        if resolved is None:
            return None

        source_type, symbol = resolved
        points = PositionTrendService._fetch_intraday_history(symbol)
        return PositionTrendService._build_payload(
            source_type=source_type,
            symbol=symbol,
            points=points,
        )

    @staticmethod
    def build_snapshot_for_position(position: Position) -> dict:
        trend = PositionTrendService.build_for_position(position)
        quote_symbol = PositionTrendService._quote_symbol_for_position(position)
        return {
            "position_id": position.id,
            "trend": trend,
            "today_change_pct": (
                PositionTrendService._fetch_realtime_change_pct(quote_symbol)
                if quote_symbol
                else None
            ),
        }

    @staticmethod
    def _resolve_source_symbol(position: Position) -> Optional[tuple[str, str]]:
        instrument = position.instrument
        if instrument is None:
            return None

        if PositionTrendService._uses_own_market_data(instrument):
            return "instrument", instrument.symbol

        tracking_index = (getattr(instrument, "tracking_index", "") or "").strip()
        if tracking_index:
            return "tracking_index", tracking_index
        return None

    @staticmethod
    def _quote_symbol_for_position(position: Position) -> Optional[str]:
        resolved = PositionTrendService._resolve_source_symbol(position)
        if resolved is None:
            return None
        return resolved[1]

    @staticmethod
    def _uses_own_market_data(instrument) -> bool:
        return (
            instrument.trade_mode == TradeMode.EXCHANGE_TRADED.value
            or getattr(instrument, "dca_confirm_cycle", None) == 0
        )

    @staticmethod
    def _fetch_intraday_history(symbol: str) -> list[dict]:
        errors = []
        for candidate in PositionTrendService._symbol_candidates(symbol):
            sina_symbol = PositionTrendService._sina_symbol(candidate)
            if not sina_symbol:
                continue
            try:
                points = PositionTrendService._fetch_sina_intraday_points(sina_symbol)
                if points:
                    return points
            except Exception as exc:
                errors.append(f"{sina_symbol}: {exc}")

        logger.warning(
            "Failed to fetch intraday trend for %s: %s",
            symbol,
            "; ".join(errors[-3:]),
        )
        return []

    @staticmethod
    def _fetch_realtime_change_pct(symbol: str) -> Optional[float]:
        errors = []
        for candidate in PositionTrendService._symbol_candidates(symbol):
            for sina_symbol in PositionTrendService._sina_quote_symbols(candidate):
                try:
                    response = requests.get(
                        f"{PositionTrendService.SINA_QUOTE_URL}{sina_symbol}",
                        headers=PositionTrendService.HEADERS,
                        timeout=10,
                    )
                    response.raise_for_status()
                    raw_text = response.content.decode("gbk", errors="ignore")
                    change_pct = PositionTrendService._parse_sina_quote_change_pct(
                        raw_text,
                        sina_symbol,
                    )
                    if change_pct is not None:
                        return change_pct
                except Exception as exc:
                    errors.append(f"{sina_symbol}: {exc}")

        logger.warning(
            "Failed to fetch realtime quote for %s: %s",
            symbol,
            "; ".join(errors[-3:]),
        )
        return None

    @staticmethod
    def _parse_sina_quote_change_pct(raw_text: str, sina_symbol: str) -> Optional[float]:
        for line in raw_text.splitlines():
            line = line.strip()
            if f"hq_str_{sina_symbol}" not in line or '="' not in line:
                continue
            fields = line.split('="', 1)[1].rstrip('";').split(",")
            if sina_symbol.startswith("s_"):
                pct = to_float(fields[3] if len(fields) > 3 else None)
                return round_metric(pct / 100) if pct is not None else None

            if len(fields) < 4:
                continue
            prev_close = to_float(fields[2])
            latest = to_float(fields[3])
            if prev_close is None or prev_close <= 0 or latest is None:
                return None
            return round_metric(latest / prev_close - 1)
        return None

    @staticmethod
    def _fetch_sina_intraday_points(sina_symbol: str) -> list[dict]:
        response = requests.get(
            PositionTrendService.SINA_INTRADAY_URL,
            params={
                "symbol": sina_symbol,
                "scale": 1,
                "ma": "no",
                "datalen": 242,
            },
            headers=PositionTrendService.HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            data = data.get("data") or data.get("records") or []
        if not isinstance(data, list):
            return []
        return PositionTrendService._intraday_points_from_records(data)

    @staticmethod
    def _intraday_points_from_records(records: list[dict]) -> list[dict]:
        points = []
        for record in records:
            value = to_float(record.get("close"))
            if value is None or value <= 0:
                continue
            time_value = (
                record.get("day")
                or record.get("time")
                or record.get("datetime")
                or record.get("date")
            )
            if not time_value:
                continue
            points.append(
                {
                    "time": str(time_value),
                    "value": float(value),
                }
            )
        return points

    @staticmethod
    def _symbol_candidates(symbol: str) -> list[str]:
        normalized = symbol.strip()
        if not normalized:
            return []

        candidates = [normalized]
        if "." in normalized:
            code, market = normalized.split(".", 1)
            if market.upper() in {"CSI", "CNI"}:
                candidates.extend([f"{code}.SH", f"sh{code}"])
        elif normalized.isdigit() and len(normalized) == 6:
            market = "SH" if normalized.startswith(("0", "3", "9")) else "SZ"
            candidates.append(f"{normalized}.{market}")

        seen = set()
        unique = []
        for candidate in candidates:
            if candidate not in seen:
                unique.append(candidate)
                seen.add(candidate)
        return unique

    @staticmethod
    def _sina_symbol(symbol: str) -> str:
        normalized = symbol.strip()
        if normalized.startswith(("sh", "sz", "bj")):
            return normalized
        if "." in normalized:
            code, market = normalized.split(".", 1)
            market = market.upper()
            if market in {"SH", "SSE", "CSI", "CNI"}:
                return f"sh{code}"
            if market in {"SZ", "SZSE"}:
                return f"sz{code}"
            if market in {"BJ", "BSE"}:
                return f"bj{code}"
            return ""
        if normalized.isdigit() and len(normalized) == 6:
            market = "sh" if normalized.startswith(("0", "5", "6", "9")) else "sz"
            return f"{market}{normalized}"
        return normalized

    @staticmethod
    def _sina_quote_symbols(symbol: str) -> list[str]:
        base_symbol = PositionTrendService._sina_symbol(symbol)
        if not base_symbol:
            return []

        candidates = [base_symbol]
        if PositionTrendService._looks_like_index_symbol(symbol, base_symbol):
            candidates.insert(0, f"s_{base_symbol}")

        seen = set()
        unique = []
        for candidate in candidates:
            if candidate not in seen:
                unique.append(candidate)
                seen.add(candidate)
        return unique

    @staticmethod
    def _looks_like_index_symbol(original_symbol: str, sina_symbol: str) -> bool:
        normalized = original_symbol.strip().upper()
        if "." in normalized:
            _, market = normalized.split(".", 1)
            if market in {"CSI", "CNI"}:
                return True

        code = sina_symbol[2:] if sina_symbol.startswith(("sh", "sz")) else sina_symbol
        return code.startswith(("000", "399", "930", "931", "932"))

    @staticmethod
    def _build_payload(source_type: str, symbol: str, points: list[dict]) -> Optional[dict]:
        if len(points) < 2:
            return None

        first = points[0]["value"]
        last = points[-1]["value"]
        change_pct = (last / first - 1) if first > 0 else 0

        return {
            "source_type": source_type,
            "interval": "intraday",
            "symbol": symbol,
            "points": points,
            "change_pct": round_metric(change_pct, 4),
        }
