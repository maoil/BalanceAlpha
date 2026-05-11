import { useState } from "react";
import { RefreshCw } from "lucide-react";

import { api } from "../api/endpoints";
import { DataState, Notice } from "../components/DataState";
import { useAsyncData, useMutationStatus } from "../hooks";

type StrategySignal = {
  instrument_id: number;
  symbol: string;
  name: string;
  strategy?: string;
  signal: string;
  signal_type?: string;
  explanation?: string;
  latest_price?: number;
  latest_date?: string;
  data_source?: string;
  indicators?: Record<string, unknown>;
};

export function SignalsPage() {
  const [detail, setDetail] = useState<StrategySignal | null>(null);
  const signals = useAsyncData(() => api.strategySignals(), []);
  const mutation = useMutationStatus();

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>策略信号</h1>
          <p>基于 Python 策略代码生成的实时交易信号</p>
        </div>
        <button
          className="primary-button"
          disabled={mutation.busy || signals.loading}
          type="button"
          onClick={() =>
            mutation.run(async () => {
              await signals.reload();
            }, "信号已刷新")
          }
        >
          <RefreshCw aria-hidden="true" />
          刷新信号
        </button>
      </div>

      <Notice message={mutation.message} />
      <Notice message={mutation.error} tone="error" />

      <section className="content-grid">
        <div className="panel wide">
          <div className="panel-header">
            <h2>信号列表</h2>
            <span>{signals.data?.length || 0} 个产品</span>
          </div>
          <DataState loading={signals.loading} error={signals.error}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>代码</th>
                  <th>名称</th>
                  <th>策略</th>
                  <th>信号</th>
                  <th>最新价</th>
                  <th>数据来源</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                {signals.data?.map((signal: StrategySignal) => (
                  <tr
                    key={signal.instrument_id}
                    className="clickable-row"
                    onClick={() => setDetail(signal)}
                  >
                    <td>{signal.symbol}</td>
                    <td>{signal.name}</td>
                    <td>{signal.strategy || "-"}</td>
                    <td>
                      <span className={`signal-badge ${signal.signal_type || "unknown"}`}>
                        {signal.signal}
                      </span>
                    </td>
                    <td>{signal.latest_price?.toFixed(4) || "-"}</td>
                    <td>{signal.data_source || "-"}</td>
                    <td className="explanation-cell">{signal.explanation || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </DataState>
        </div>

        {detail && (
          <div className="panel">
            <div className="panel-header">
              <h2>信号详情</h2>
              <button
                className="ghost-button small"
                type="button"
                onClick={() => setDetail(null)}
              >
                关闭
              </button>
            </div>
            <div className="detail-content">
              <dl className="detail-list">
                <dt>产品</dt>
                <dd>{detail.symbol} - {detail.name}</dd>
                <dt>策略</dt>
                <dd>{detail.strategy || "-"}</dd>
                <dt>信号</dt>
                <dd>
                  <span className={`signal-badge ${detail.signal_type || "unknown"}`}>
                    {detail.signal}
                  </span>
                </dd>
                <dt>最新价</dt>
                <dd>{detail.latest_price?.toFixed(4) || "-"}</dd>
                <dt>数据日期</dt>
                <dd>{detail.latest_date || "-"}</dd>
                <dt>说明</dt>
                <dd>{detail.explanation || "-"}</dd>
              </dl>
              {detail.indicators && Object.keys(detail.indicators).length > 0 && (
                <>
                  <h3>技术指标</h3>
                  <dl className="detail-list">
                    {Object.entries(detail.indicators).map(([key, value]) => (
                      <div key={key}>
                        <dt>{key}</dt>
                        <dd>{typeof value === "number" ? value.toFixed(4) : String(value)}</dd>
                      </div>
                    ))}
                  </dl>
                </>
              )}
            </div>
          </div>
        )}
      </section>

      <style>{`
        .signal-badge {
          display: inline-block;
          padding: 2px 8px;
          border-radius: 4px;
          font-weight: 600;
          font-size: 0.875rem;
        }
        .signal-badge.buy {
          background-color: #fee2e2;
          color: #dc2626;
        }
        .signal-badge.sell {
          background-color: #dcfce7;
          color: #16a34a;
        }
        .signal-badge.hold {
          background-color: #fef3c7;
          color: #d97706;
        }
        .signal-badge.unknown {
          background-color: #f3f4f6;
          color: #6b7280;
        }
        .explanation-cell {
          max-width: 300px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .clickable-row {
          cursor: pointer;
        }
        .clickable-row:hover {
          background-color: var(--color-surface-hover, #f9fafb);
        }
        .detail-content {
          padding: 1rem;
        }
        .detail-list {
          display: grid;
          grid-template-columns: auto 1fr;
          gap: 0.5rem 1rem;
        }
        .detail-list dt {
          font-weight: 500;
          color: var(--color-text-secondary, #6b7280);
        }
        .detail-list dd {
          margin: 0;
        }
        .detail-content h3 {
          margin-top: 1rem;
          margin-bottom: 0.5rem;
          font-size: 0.875rem;
          font-weight: 600;
        }
      `}</style>
    </div>
  );
}
