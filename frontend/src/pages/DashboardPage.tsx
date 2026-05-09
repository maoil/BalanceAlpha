import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "../api/endpoints";
import { DataState, EmptyState } from "../components/DataState";
import { useAsyncData } from "../hooks";
import {
  compactJson,
  formatDate,
  formatNumber,
  formatPercent,
  formatSignedNumber,
  valueTone,
} from "../utils/format";

export function DashboardPage() {
  const dashboard = useAsyncData(() => api.dashboard(), []);
  const trend = useAsyncData(() => api.assetTrend(30), []);
  const performance = useAsyncData(() => api.performanceSummary(), []);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>仪表盘</h1>
          <p>账户资产、收益、信号和市场情绪的统一视图。</p>
        </div>
        <button className="ghost-button" type="button" onClick={() => dashboard.reload()}>
          刷新
        </button>
      </div>

      <DataState loading={dashboard.loading} error={dashboard.error}>
        {dashboard.data && (
          <>
            <section className="metric-grid" aria-label="资产概览">
              <Metric label="总资产" value={formatNumber(dashboard.data.totals.market_value)} />
              <Metric label="持仓成本" value={formatNumber(dashboard.data.totals.cost)} />
              <Metric
                label="浮动盈亏"
                value={formatNumber(dashboard.data.totals.unrealized_pnl)}
                tone={valueTone(dashboard.data.totals.unrealized_pnl)}
              />
              <Metric
                label="收益率"
                value={formatPercent(dashboard.data.totals.unrealized_pnl_pct)}
                tone={valueTone(dashboard.data.totals.unrealized_pnl_pct)}
              />
              <Metric label="持仓数" value={String(dashboard.data.totals.position_count)} />
            </section>

            <section className="content-grid">
              <div className="panel wide">
                <div className="panel-header">
                  <h2>每日累计浮动盈亏</h2>
                  <span>近 30 日</span>
                </div>
                <DataState loading={trend.loading} error={trend.error}>
                  {trend.data?.series?.length ? (
                    <div className="chart-wrap">
                      <ResponsiveContainer width="100%" height={260}>
                        <AreaChart data={trend.data.series}>
                          <defs>
                            <linearGradient id="assetFill" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#b03a2e" stopOpacity={0.22} />
                              <stop offset="95%" stopColor="#b03a2e" stopOpacity={0.02} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="#dde5e1" />
                          <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                          <YAxis
                            tick={{ fontSize: 12 }}
                            tickFormatter={(value) => formatSignedNumber(Number(value), 0)}
                          />
                          <Tooltip
                            formatter={(value, name) => [
                              formatSignedNumber(Number(value)),
                              name === "unrealized_pnl" ? "累计浮动盈亏" : name,
                            ]}
                          />
                          <Area
                            type="monotone"
                            dataKey="unrealized_pnl"
                            stroke="#b03a2e"
                            fill="url(#assetFill)"
                            strokeWidth={2}
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <EmptyState label="暂无盈亏曲线" />
                  )}
                </DataState>
              </div>

              <div className="panel">
                <div className="panel-header">
                  <h2>绩效摘要</h2>
                  <span>{formatDate(performance.data?.as_of_date)}</span>
                </div>
                <DataState loading={performance.loading} error={performance.error}>
                  <dl className="kv-list">
                    <KV label="当日盈亏" value={formatNumber(performance.data?.today_pnl)} />
                    <KV
                      label="累计收益"
                      value={formatPercent(performance.data?.cumulative_return)}
                    />
                    <KV
                      label="年化收益"
                      value={formatPercent(performance.data?.annualized_return)}
                    />
                    <KV
                      label="较昨日"
                      value={formatNumber(performance.data?.change_vs_yesterday)}
                    />
                  </dl>
                </DataState>
              </div>
            </section>

            <section className="content-grid">
              <div className="panel">
                <div className="panel-header">
                  <h2>账户分布</h2>
                  <span>{dashboard.data.accounts.length} 个账户</span>
                </div>
                {dashboard.data.accounts.length ? (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>账户</th>
                        <th>市值</th>
                        <th>盈亏</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dashboard.data.accounts.map((account) => (
                        <tr key={account.id}>
                          <td>{account.account_name}</td>
                          <td>{formatNumber(account.summary.market_value)}</td>
                          <td className={valueTone(account.summary.unrealized_pnl)}>
                            {formatNumber(account.summary.unrealized_pnl)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <EmptyState />
                )}
              </div>

              <div className="panel">
                <div className="panel-header">
                  <h2>待处理信号</h2>
                  <span>{dashboard.data.pending_signals.length} 条</span>
                </div>
                {dashboard.data.pending_signals.length ? (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>产品</th>
                        <th>动作</th>
                        <th>优先级</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dashboard.data.pending_signals.slice(0, 6).map((signal) => (
                        <tr key={signal.id}>
                          <td>{signal.instrument?.name || signal.instrument_id}</td>
                          <td>{signal.signal_type}</td>
                          <td>{signal.priority}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <EmptyState label="暂无待处理信号" />
                )}
              </div>

              <div className="panel">
                <div className="panel-header">
                  <h2>近期交易</h2>
                  <span>{dashboard.data.recent_trades.length} 条</span>
                </div>
                {dashboard.data.recent_trades.length ? (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>日期</th>
                        <th>产品</th>
                        <th>金额</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dashboard.data.recent_trades.map((trade) => (
                        <tr key={trade.id}>
                          <td>{formatDate(trade.trade_date)}</td>
                          <td>{trade.instrument?.symbol || trade.instrument_id}</td>
                          <td>{formatNumber(trade.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <EmptyState label="暂无交易" />
                )}
              </div>

              <div className="panel">
                <div className="panel-header">
                  <h2>市场情绪</h2>
                  <span>外部数据</span>
                </div>
                <pre className="json-block">{compactJson(dashboard.data.market_sentiment)}</pre>
              </div>
            </section>
          </>
        )}
      </DataState>
    </div>
  );
}

function Metric({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="metric-tile">
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  );
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}
