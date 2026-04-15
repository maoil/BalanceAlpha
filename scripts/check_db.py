import sqlite3

DB = r"c:\Users\guangxin.yang\PycharmProjects\BalanceAlpha\data\balancealpha.db"
conn = sqlite3.connect(DB)
c = conn.cursor()

print("=" * 80)
print("All instruments: market data & signal check")
print("=" * 80)

instruments = c.execute(
    "SELECT id, symbol, name, status FROM instruments WHERE status='active' ORDER BY id"
).fetchall()

no_data = []
has_data = []

for inst_id, symbol, name, status in instruments:
    # Market data
    md = c.execute(
        "SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM market_data WHERE instrument_id=?",
        (inst_id,)
    ).fetchone()
    md_count, md_min, md_max = md

    # Position
    pos = c.execute(
        "SELECT quantity, market_price, market_value, weight_in_account "
        "FROM positions WHERE instrument_id=? AND position_status='open'",
        (inst_id,)
    ).fetchone()

    # Latest signal
    sig = c.execute(
        "SELECT signal_type, score, explanation FROM signals WHERE instrument_id=? "
        "ORDER BY signal_date DESC LIMIT 1",
        (inst_id,)
    ).fetchone()

    # Assignment
    sa = c.execute(
        "SELECT target_weight_lower, target_weight_upper FROM strategy_assignments "
        "WHERE instrument_id=? AND status='active'",
        (inst_id,)
    ).fetchone()

    weight = pos[3] if pos else 0
    target_mid = (sa[0] + sa[1]) / 2 if sa else 0

    print(f"\n{symbol} ({name})")
    print(f"  Position:    qty={pos[0]}, price={pos[1]}, value={pos[2]:.1f}, weight={weight:.2%}" if pos else "  Position:    NONE")
    print(f"  Target:      [{sa[0]:.0%}, {sa[1]:.0%}], mid={target_mid:.1%}" if sa else "  Target:      NO ASSIGNMENT")

    if md_count > 0:
        print(f"  MarketData:  {md_count} rows, range=[{md_min}, {md_max}]")
        has_data.append(symbol)
    else:
        print(f"  MarketData:  !! EMPTY - NO DATA !!")
        no_data.append(symbol)

    if sig:
        sig_type, score, expl = sig
        print(f"  Signal:      {sig_type}, score={score}")
        # Truncate long explanations for readability
        if expl and len(expl) > 60:
            expl = expl[:60] + "..."
        print(f"               {expl}")
    else:
        print(f"  Signal:      NONE")

    if target_mid > 0 and weight > 0:
        dev = abs(weight - target_mid) / target_mid
        flag = " << SHOULD REBALANCE" if dev > 0.20 else ""
        print(f"  Deviation:   {dev:.1%}{flag}")

print(f"\n{'=' * 80}")
print(f"SUMMARY")
print(f"{'=' * 80}")
print(f"  Total instruments:     {len(instruments)}")
print(f"  With market data:      {len(has_data)}  {has_data}")
print(f"  WITHOUT market data:   {len(no_data)}  {no_data}")
if no_data:
    print(f"\n  >> These {len(no_data)} instruments need historical data imported!")
    print(f"  >> Go to Product Management page and click the history button for each.")

conn.close()
