"""
诊断信号生成为0的原因
逐步检查：账户 → 策略绑定 → 产品状态 → 行情数据
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.account import Account
from app.models.instrument import Instrument
from app.models.strategy_assignment import StrategyAssignment
from app.models.market_data import MarketData
from app.models.position import Position
from app.models.signal import Signal

app = create_app()

with app.app_context():
    print("=" * 60)
    print("BalanceAlpha 信号生成诊断")
    print("=" * 60)

    # 1. 检查账户
    accounts = Account.query.all()
    active_accounts = [a for a in accounts if a.status == "active"]
    print(f"\n[1] 账户总数: {len(accounts)}, 活跃账户: {len(active_accounts)}")
    for a in accounts:
        print(f"    - id={a.id}, code={a.account_code}, type={a.account_type}, status={a.status}")

    if not active_accounts:
        print("\n❌ 没有活跃账户！这是信号为0的原因。")
        sys.exit(0)

    # 2. 检查策略绑定
    all_assignments = StrategyAssignment.query.all()
    active_assignments = [sa for sa in all_assignments if sa.status == "active"]
    print(f"\n[2] 策略绑定总数: {len(all_assignments)}, 活跃绑定: {len(active_assignments)}")
    for sa in all_assignments:
        inst = Instrument.query.get(sa.instrument_id)
        inst_name = f"{inst.symbol} ({inst.name})" if inst else "未知产品"
        print(f"    - id={sa.id}, account_id={sa.account_id}, instrument={inst_name}, "
              f"template_id={sa.template_id}, status={sa.status}")

    if not active_assignments:
        print("\n❌ 没有活跃的策略绑定！这是信号为0的原因。")
        print("   需要在「产品管理」中为产品绑定策略模板和账户。")
        sys.exit(0)

    # 3. 检查对应的产品状态
    print(f"\n[3] 检查策略绑定对应的产品状态:")
    problem_found = False
    for sa in active_assignments:
        inst = Instrument.query.get(sa.instrument_id)
        if not inst:
            print(f"    ❌ 绑定 id={sa.id}: instrument_id={sa.instrument_id} 不存在！")
            problem_found = True
        elif inst.status != "active":
            print(f"    ⚠️  绑定 id={sa.id}: {inst.symbol} ({inst.name}) 状态为 '{inst.status}'，不是 'active'")
            problem_found = True
        else:
            print(f"    ✅ 绑定 id={sa.id}: {inst.symbol} ({inst.name}) 状态=active")

    # 4. 检查所有产品
    instruments = Instrument.query.all()
    active_instruments = [i for i in instruments if i.status == "active"]
    print(f"\n[4] 产品总数: {len(instruments)}, 活跃产品: {len(active_instruments)}")
    for i in instruments:
        # 检查该产品是否有策略绑定
        has_assignment = StrategyAssignment.query.filter_by(
            instrument_id=i.id, status="active"
        ).first()
        binding_status = "✅ 已绑定策略" if has_assignment else "❌ 未绑定策略"
        
        # 检查行情数据
        md_count = MarketData.query.filter_by(instrument_id=i.id).count()
        latest_md = MarketData.query.filter_by(instrument_id=i.id).order_by(
            MarketData.trade_date.desc()
        ).first()
        md_info = f"行情{md_count}条, 最新={latest_md.trade_date}" if latest_md else "无行情数据"
        
        print(f"    - id={i.id}, {i.symbol} ({i.name}), status={i.status}, "
              f"{binding_status}, {md_info}")

    # 5. 检查持仓
    positions = Position.query.filter_by(position_status="open").all()
    print(f"\n[5] 活跃持仓数: {len(positions)}")
    for p in positions:
        inst = Instrument.query.get(p.instrument_id)
        inst_name = f"{inst.symbol}" if inst else "?"
        print(f"    - {inst_name}, account_id={p.account_id}, qty={p.quantity}, "
              f"cost={p.avg_cost:.4f}, price={p.market_price:.4f}")

    # 6. 检查已有信号
    signals = Signal.query.order_by(Signal.signal_date.desc()).limit(10).all()
    print(f"\n[6] 最近信号 (最多10条):")
    if signals:
        for s in signals:
            inst = Instrument.query.get(s.instrument_id)
            inst_name = f"{inst.symbol}" if inst else "?"
            print(f"    - {s.signal_date} | {inst_name} | {s.signal_type} | "
                  f"status={s.status} | {s.explanation[:40] if s.explanation else ''}")
    else:
        print("    (无历史信号记录)")

    # 7. 总结
    print("\n" + "=" * 60)
    print("诊断总结")
    print("=" * 60)
    
    if not active_assignments:
        print("🔴 根本原因：没有活跃的策略绑定 (strategy_assignments)")
        print("   解决方法：为产品创建策略绑定，关联到账户和策略模板")
    elif all(
        not Instrument.query.get(sa.instrument_id) or 
        Instrument.query.get(sa.instrument_id).status != "active"
        for sa in active_assignments
    ):
        print("🔴 根本原因：所有绑定的产品状态都不是 'active'")
        print("   解决方法：将产品状态改为 'active'")
    else:
        valid_count = sum(
            1 for sa in active_assignments
            if Instrument.query.get(sa.instrument_id) and 
               Instrument.query.get(sa.instrument_id).status == "active"
        )
        print(f"✅ 数据链路看起来正常：{len(active_accounts)} 个账户, "
              f"{valid_count} 个有效绑定")
        print("   如果仍然生成0个信号，可能是代码逻辑问题，需进一步调试")
