"""
Batch fetch historical market data for all active instruments that have no data.
Requires Flask app context to use the FundDataFetcher service.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models.instrument import Instrument
from app.models.market_data import MarketData
from app.services.fund_data_fetcher import FundDataFetcher

app = create_app()

with app.app_context():
    instruments = Instrument.query.filter_by(status="active").all()
    print(f"Total active instruments: {len(instruments)}")

    for inst in instruments:
        md_count = MarketData.query.filter_by(instrument_id=inst.id).count()
        if md_count > 0:
            print(f"\n[SKIP] {inst.symbol} ({inst.name}): already has {md_count} rows")
            continue

        print(f"\n[FETCH] {inst.symbol} ({inst.name}), type={inst.trade_mode} ...")
        try:
            result = FundDataFetcher.fetch_and_import_history(inst.id, days=365)
            if "error" in result:
                print(f"  ERROR: {result['error']}")
            else:
                print(f"  OK: imported={result['imported']}, skipped={result['skipped']}")
        except Exception as e:
            print(f"  EXCEPTION: {e}")

    print("\nDone!")
