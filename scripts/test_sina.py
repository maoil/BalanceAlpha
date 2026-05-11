import sys
sys.path.insert(0, '.')

from app.backtesting.providers import sina_etf_daily

df = sina_etf_daily('159819.SZ', start='2026-05-01')
print('ETF data (159819.SZ) from Sina:')
print(df.tail())
print(f'Latest date: {df.index[-1]}')
print(f'Latest close: {df.iloc[-1]["Close"]}')
