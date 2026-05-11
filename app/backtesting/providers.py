"""
Data source providers for backtesting.

Each provider function fetches remote OHLCV data and returns a standardized DataFrame.

Standard return format:
- Ascending DatetimeIndex
- Columns: Open, High, Low, Close, Volume
"""

import json
import logging
import math
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def tencent_daily_ohlcv(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch daily OHLCV data from Tencent Finance API.

    Args:
        symbol: Stock/ETF symbol in format like "159819.SZ" or "sh600000"
        start: Start date in ISO format (YYYY-MM-DD)
        end: End date in ISO format (YYYY-MM-DD)

    Returns:
        DataFrame with DatetimeIndex and OHLCV columns
    """
    if "." in symbol:
        code, market = symbol.split(".")
        if market.upper() in ("SZ", "SZSE"):
            symbol = f"sz{code}"
        elif market.upper() in ("SH", "SSE"):
            symbol = f"sh{code}"
        else:
            symbol = f"{market.lower()}{code}"

    end_date = end or date.today().isoformat()
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,{start or ''},9999,qfq"

    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://gu.qq.com/",
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)

            if payload.get("code") != 0:
                raise RuntimeError(f"Tencent API error: {payload.get('msg', 'Unknown error')}")

            data = payload.get("data", {})
            kline_key = list(data.keys())[0] if data else None
            if not kline_key:
                raise RuntimeError("No data returned from Tencent API")

            kline_data = data[kline_key]
            day_data = kline_data.get("qfqday") or kline_data.get("day")
            if not day_data:
                raise RuntimeError("No daily data in response")

            df = pd.DataFrame(
                day_data,
                columns=["Date", "Open", "Close", "High", "Low", "Volume"],
            )
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date")

            for col in ["Open", "High", "Low", "Close"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")

            df = df[["Open", "High", "Low", "Close", "Volume"]]
            df = df.sort_index()

            if start:
                df = df[df.index >= pd.Timestamp(start)]
            if end:
                df = df[df.index <= pd.Timestamp(end)]

            if df.empty:
                raise RuntimeError(f"No data returned for symbol {symbol}")

            logger.info(
                f"Fetched {len(df)} rows from Tencent for {symbol}: "
                f"{df.index[0].date()} to {df.index[-1].date()}"
            )
            return df

        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"Failed to fetch data from Tencent after 3 attempts: {e}") from e
            time.sleep(1 + attempt)

    raise RuntimeError("Failed to fetch data from Tencent")


def eastmoney_fund_nav(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    page_size: int = 20,
) -> pd.DataFrame:
    """
    Fetch fund NAV data from Eastmoney and convert to OHLCV format.

    For funds, Open/High/Low/Close are all set to the NAV value,
    and Volume is set to NaN.

    Args:
        symbol: Fund code (e.g., "020840")
        start: Start date in ISO format (YYYY-MM-DD)
        end: End date in ISO format (YYYY-MM-DD)
        page_size: Page size for API pagination

    Returns:
        DataFrame with DatetimeIndex and OHLCV columns
    """
    if "." in symbol:
        symbol = symbol.split(".")[0]

    records = []
    page = 1
    total_count = None

    while total_count is None or len(records) < total_count:
        params = {
            "fundCode": symbol,
            "pageIndex": page,
            "pageSize": page_size,
            "startDate": start or "",
            "endDate": end or "",
            "_": int(time.time() * 1000),
        }
        url = "https://api.fund.eastmoney.com/f10/lsjz?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={
                "Referer": "https://fundf10.eastmoney.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        )

        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    payload = json.load(response)
                if payload.get("Data") is not None:
                    break
            except Exception:
                pass
            if attempt == 2:
                raise RuntimeError(f"Empty response data while fetching page {page}")
            time.sleep(1 + attempt)

        if payload.get("ErrCode") != 0:
            raise RuntimeError(f"Failed to fetch fund NAV: {payload.get('ErrMsg')}")

        total_count = payload["TotalCount"]
        batch = payload["Data"]["LSJZList"]
        if not batch:
            break

        records.extend(batch)
        page += 1
        time.sleep(0.2)

    nav = pd.DataFrame(records)
    if nav.empty:
        raise RuntimeError(f"No NAV records returned for fund {symbol}")

    nav["Date"] = pd.to_datetime(nav["FSRQ"])
    nav["NetValue"] = pd.to_numeric(
        nav["LJJZ"].where(nav["LJJZ"].ne(""), nav["DWJZ"]),
        errors="coerce",
    )
    nav = nav.sort_values("Date").drop_duplicates("Date")
    nav = nav.set_index("Date")[["NetValue"]]

    df = pd.DataFrame(index=nav.index)
    df["Open"] = nav["NetValue"]
    df["High"] = nav["NetValue"]
    df["Low"] = nav["NetValue"]
    df["Close"] = nav["NetValue"]
    df["Volume"] = math.nan
    df = df.sort_index()

    if start:
        df = df[df.index >= pd.Timestamp(start)]
    if end:
        df = df[df.index <= pd.Timestamp(end)]

    logger.info(
        f"Fetched {len(df)} rows from Eastmoney for fund {symbol}: "
        f"{df.index[0].date()} to {df.index[-1].date()}"
    )
    return df


def sina_etf_daily(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    datalen: int = 300,
) -> pd.DataFrame:
    """
    Fetch daily OHLCV data for ETF/Index from Sina Finance.
    
    This API works reliably and returns recent historical data.
    
    Args:
        symbol: Symbol in format like "159819.SZ" or "sh000977"
        start: Start date in ISO format
        end: End date in ISO format
        datalen: Number of days to fetch
    
    Returns:
        DataFrame with DatetimeIndex and OHLCV columns
    """
    if "." in symbol:
        code, market = symbol.split(".")
        market = market.upper()
        if market in ("SH", "SSE"):
            sina_symbol = f"sh{code}"
        else:
            sina_symbol = f"sz{code}"
    else:
        sina_symbol = symbol
    
    url = (
        f"https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?"
        f"symbol={sina_symbol}&scale=240&ma=no&datalen={datalen}"
    )
    
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://finance.sina.com.cn/",
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.load(response)
            
            if not data:
                raise RuntimeError(f"No data returned for {symbol}")
            
            df = pd.DataFrame(data)
            df["Date"] = pd.to_datetime(df["day"])
            df = df.set_index("Date")
            
            for col in ["open", "high", "low", "close"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
            
            df = df.rename(columns={
                "open": "Open",
                "high": "High", 
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            })
            df = df[["Open", "High", "Low", "Close", "Volume"]]
            df = df.sort_index()
            
            if start:
                df = df[df.index >= pd.Timestamp(start)]
            if end:
                df = df[df.index <= pd.Timestamp(end)]
            
            if df.empty:
                raise RuntimeError(f"No data in range for {symbol}")
            
            logger.info(
                f"Fetched {len(df)} rows from Sina for {symbol}: "
                f"{df.index[0].date()} to {df.index[-1].date()}"
            )
            return df
            
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"Failed to fetch from Sina after 3 attempts: {e}") from e
            time.sleep(1 + attempt)
    
    raise RuntimeError(f"Failed to fetch data for {symbol}")


def eastmoney_index_daily(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch daily OHLCV data for index/ETF from Eastmoney.
    
    Supports:
    - Index: 000977.SH (CS人工智能), 000300.SH (沪深300)
    - ETF: 159819.SZ (人工智能ETF)
    
    Args:
        symbol: Symbol in format like "000977.SH" or "159819.SZ"
        start: Start date in ISO format
        end: End date in ISO format
    
    Returns:
        DataFrame with DatetimeIndex and OHLCV columns
    """
    if "." in symbol:
        code, market = symbol.split(".")
        market = market.upper()
    else:
        code = symbol
        market = "SH" if symbol.startswith("0") or symbol.startswith("3") else "SZ"
    
    # 东方财富 secid: 1=上海, 0=深圳
    if market in ("SH", "SSE"):
        secid = f"1.{code}"
    else:
        secid = f"0.{code}"
    
    # 计算获取天数
    if start:
        start_date = datetime.fromisoformat(start)
        days = (datetime.now() - start_date).days + 30
    else:
        days = 365
    
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get?"
        f"secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57"
        f"&klt=101&fqt=1&end=20500101&lmt={days}"
    )
    
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://quote.eastmoney.com/",
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            
            data = payload.get("data")
            if not data or not data.get("klines"):
                raise RuntimeError(f"No data returned for {symbol}")
            
            records = []
            for line in data["klines"]:
                parts = line.split(",")
                if len(parts) >= 6:
                    records.append({
                        "Date": parts[0],
                        "Open": float(parts[1]),
                        "Close": float(parts[2]),
                        "High": float(parts[3]),
                        "Low": float(parts[4]),
                        "Volume": float(parts[5]) if parts[5] != "-" else 0,
                    })
            
            df = pd.DataFrame(records)
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date")
            df = df[["Open", "High", "Low", "Close", "Volume"]]
            df = df.sort_index()
            
            if start:
                df = df[df.index >= pd.Timestamp(start)]
            if end:
                df = df[df.index <= pd.Timestamp(end)]
            
            if df.empty:
                raise RuntimeError(f"No data in range for {symbol}")
            
            logger.info(
                f"Fetched {len(df)} rows from Eastmoney for {symbol}: "
                f"{df.index[0].date()} to {df.index[-1].date()}"
            )
            return df
            
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"Failed to fetch data after 3 attempts: {e}") from e
            time.sleep(1 + attempt)
    
    raise RuntimeError(f"Failed to fetch data for {symbol}")


__all__ = ["tencent_daily_ohlcv", "eastmoney_fund_nav", "eastmoney_index_daily", "sina_etf_daily"]
