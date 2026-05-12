import { FormEvent, useState } from "react";

import { api } from "../api/endpoints";
import { DateField } from "../components/DateField";
import { DataState, Notice } from "../components/DataState";
import { useAsyncData, useMutationStatus } from "../hooks";
import { formatDate, formatNumber, formatSignedNumber, valueTone } from "../utils/format";
import type { BacktestRun } from "../types";

export function BacktestsPage() {
  const [selected, setSelected] = useState<BacktestRun | null>(null);
  const instruments = useAsyncData(() => api.instruments({ status: "active" }), []);
  const runs = useAsyncData(() => api.backtests(100), []);
  const mutation = useMutationStatus();

  async function createBacktest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    await mutation.run(async () => {
      const created = await api.createBacktest({
        run_name: String(form.get("run_name") || ""),
        instrument_id: Number(form.get("instrument_id")),
        start_date: String(form.get("start_date")),
        end_date: String(form.get("end_date")),
        warmup_start_date: optionalString(form.get("warmup_start_date")),
        initial_capital: Number(form.get("initial_capital") || 100000),
        commission: Number(form.get("commission") || 0),
      });
      setSelected(created);
      await runs.reload();
      formElement.reset();
    }, "回测已完成");
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>策略回测</h1>
          <p>按产品运行 backtesting.py 原生回测，并查看结果摘要。</p>
        </div>
      </div>

      <Notice message={mutation.message} />
      <Notice message={mutation.error} tone="error" />

      <section className="content-grid">
        <form className="panel form-panel" onSubmit={createBacktest}>
          <div className="panel-header">
            <h2>新建回测</h2>
          </div>
          <div className="form-grid">
            <label>
              名称
              <input name="run_name" />
            </label>
            <label>
              产品
              <select name="instrument_id" required>
                <option value="">选择产品</option>
                {instruments.data?.map((instrument) => (
                  <option key={instrument.id} value={instrument.id}>
                    {instrument.symbol} {instrument.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              开始
              <DateField name="start_date" required />
            </label>
            <label>
              结束
              <DateField name="end_date" required />
            </label>
            <label>
              预热开始
              <DateField name="warmup_start_date" />
            </label>
            <label>
              初始资金
              <input
                name="initial_capital"
                defaultValue="100000"
                min="0"
                step="1000"
                type="number"
              />
            </label>
            <label>
              佣金
              <input name="commission" defaultValue="0.0003" min="0" step="0.0001" type="number" />
            </label>
          </div>
          <button className="primary-button" disabled={mutation.busy} type="submit">
            运行回测
          </button>
        </form>

        <div className="panel">
          <div className="panel-header">
            <h2>结果详情</h2>
            <span>{selected?.status || "未选择"}</span>
          </div>
          {selected ? <BacktestSummary run={selected} /> : <p className="empty-hint">点击历史回测或运行新回测查看结果</p>}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>历史回测</h2>
          <span>{runs.data?.length || 0} 条</span>
        </div>
        <DataState loading={runs.loading} error={runs.error}>
          <table className="data-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>产品</th>
                <th>区间</th>
                <th>配置</th>
                <th>状态</th>
                <th>创建时间</th>
              </tr>
            </thead>
            <tbody>
              {runs.data?.map((run) => (
                <tr key={run.id} onClick={() => setSelected(run)}>
                  <td>{run.run_name}</td>
                  <td>{formatInstrument(run)}</td>
                  <td>
                    {formatDate(run.start_date)} 至 {formatDate(run.end_date)}
                  </td>
                  <td>{run.backtest_config_key || "-"}</td>
                  <td>{run.status}</td>
                  <td>{formatDate(run.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataState>
      </section>
    </div>
  );
}

function pct(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${formatNumber(value, 2)}%`;
}

function signedPct(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${formatSignedNumber(value, 2)}%`;
}

function money(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  return formatNumber(value, 2);
}

function ratio(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return formatNumber(value, 2);
}

type MetricCardProps = {
  label: string;
  value: string;
  tone?: "positive" | "negative" | "neutral";
};

function MetricCard({ label, value, tone = "neutral" }: MetricCardProps) {
  return (
    <div className="metric-card">
      <span className="metric-label">{label}</span>
      <span className={`metric-value ${tone}`}>{value}</span>
    </div>
  );
}

function BacktestSummary({ run }: { run: BacktestRun }) {
  const s = run.summary || {};
  const returnPct = s.return_pct as number | undefined;
  const buyHoldPct = s.buy_hold_return_pct as number | undefined;
  const maxDd = s.max_drawdown_pct as number | undefined;
  const sharpe = s.sharpe_ratio as number | undefined;
  const equityFinal = s.equity_final as number | undefined;
  const tradeCount = s.trade_count as number | undefined;
  const winRate = s.win_rate_pct as number | undefined;

  const beatsHold = returnPct != null && buyHoldPct != null && returnPct > buyHoldPct;

  return (
    <div className="backtest-summary">
      <div className="metric-grid">
        <MetricCard label="策略回报" value={signedPct(returnPct)} tone={valueTone(returnPct)} />
        <MetricCard label="买入持有回报" value={signedPct(buyHoldPct)} tone={valueTone(buyHoldPct)} />
        <MetricCard label="最终资金" value={money(equityFinal)} />
        <MetricCard label="最大回撤" value={pct(maxDd)} tone={maxDd != null ? "negative" : "neutral"} />
        <MetricCard label="夏普比率" value={ratio(sharpe)} tone={sharpe != null && sharpe > 1 ? "positive" : "neutral"} />
        <MetricCard label="交易次数" value={tradeCount != null ? String(tradeCount) : "-"} />
        <MetricCard label="胜率" value={pct(winRate)} />
        <MetricCard
          label="跑赢持有"
          value={returnPct != null && buyHoldPct != null ? (beatsHold ? "是" : "否") : "-"}
          tone={beatsHold ? "positive" : "negative"}
        />
      </div>

      <style>{`
        .backtest-summary { padding: 1rem; }
        .metric-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
          gap: 0.75rem;
        }
        .metric-card {
          display: flex;
          flex-direction: column;
          padding: 0.75rem;
          border-radius: 8px;
          background: var(--color-surface-alt, #f9fafb);
        }
        .metric-label {
          font-size: 0.75rem;
          color: var(--color-text-secondary, #6b7280);
          margin-bottom: 0.25rem;
        }
        .metric-value {
          font-size: 1.125rem;
          font-weight: 600;
        }
        .metric-value.positive { color: #dc2626; }
        .metric-value.negative { color: #16a34a; }
        .metric-value.neutral { color: var(--color-text-primary, #111827); }
        .empty-hint {
          padding: 2rem;
          text-align: center;
          color: var(--color-text-secondary, #6b7280);
        }
      `}</style>
    </div>
  );
}

function optionalString(value: FormDataEntryValue | null) {
  if (value === null || value === "") {
    return undefined;
  }
  return String(value);
}

function formatInstrument(run: BacktestRun) {
  if (run.instrument) {
    return `${run.instrument.symbol} ${run.instrument.name}`;
  }
  return run.instrument_id || "-";
}
