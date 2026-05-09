import { FormEvent, useState } from "react";

import { api } from "../api/endpoints";
import { DateField } from "../components/DateField";
import { DataState, Notice } from "../components/DataState";
import { useAsyncData, useMutationStatus } from "../hooks";
import { compactJson, formatDate, formatNumber } from "../utils/format";

export function SignalsPage() {
  const [accountId, setAccountId] = useState("");
  const [status, setStatus] = useState("");
  const [detail, setDetail] = useState<unknown>(null);
  const accounts = useAsyncData(() => api.accounts(), []);
  const signals = useAsyncData(
    () => api.signals({ account_id: accountId || undefined, status: status || undefined }),
    [accountId, status]
  );
  const mutation = useMutationStatus();

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const signalDate = String(new FormData(event.currentTarget).get("signal_date") || "");
    await mutation.run(async () => {
      await api.generateSignals(signalDate || undefined);
      await signals.reload();
    }, "策略信号已生成");
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>策略信号</h1>
          <p>生成、筛选和分析当前策略建议，支持 AI 分析与调仓上下文。</p>
        </div>
        <button
          className="ghost-button"
          disabled={mutation.busy}
          type="button"
          onClick={() =>
            mutation.run(
              () => api.createBatchAiAnalysis(accountId ? Number(accountId) : undefined),
              "批量 AI 分析已提交"
            )
          }
        >
          批量 AI
        </button>
      </div>

      <Notice message={mutation.message} />
      <Notice message={mutation.error} tone="error" />

      <section className="toolbar">
        <label>
          账户
          <select value={accountId} onChange={(event) => setAccountId(event.target.value)}>
            <option value="">全部</option>
            {accounts.data?.map((account) => (
              <option key={account.id} value={account.id}>
                {account.account_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          状态
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">全部</option>
            <option value="pending">待处理</option>
            <option value="done">已处理</option>
            <option value="expired">已过期</option>
          </select>
        </label>
        <form className="inline-form" onSubmit={generate}>
          <DateField aria-label="信号日期" name="signal_date" />
          <button className="primary-button" disabled={mutation.busy} type="submit">
            生成信号
          </button>
        </form>
      </section>

      <section className="content-grid">
        <div className="panel wide">
          <div className="panel-header">
            <h2>信号列表</h2>
            <span>{signals.data?.length || 0} 条</span>
          </div>
          <DataState loading={signals.loading} error={signals.error}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>账户</th>
                  <th>产品</th>
                  <th>信号</th>
                  <th>优先级</th>
                  <th>分数</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {signals.data?.map((signal) => (
                  <tr key={signal.id}>
                    <td>{formatDate(signal.signal_date)}</td>
                    <td>{signal.account?.account_name || signal.account_id}</td>
                    <td>{signal.instrument?.symbol || signal.instrument_id}</td>
                    <td>{signal.signal_type}</td>
                    <td>{signal.priority}</td>
                    <td>{formatNumber(signal.score)}</td>
                    <td>{signal.status}</td>
                    <td className="action-row">
                      <button
                        className="ghost-button small"
                        type="button"
                        onClick={() =>
                          mutation.run(async () => {
                            const result = await api.createSignalAiAnalysis(signal.id);
                            setDetail(result);
                          }, "单条 AI 分析完成")
                        }
                      >
                        AI
                      </button>
                      <button
                        className="ghost-button small"
                        type="button"
                        onClick={() =>
                          mutation.run(async () => {
                            const result = await api.rebalanceGuidance(signal.id);
                            setDetail(result);
                          }, "调仓上下文已加载")
                        }
                      >
                        调仓
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </DataState>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2>详情输出</h2>
          </div>
          <pre className="json-block">{compactJson(detail)}</pre>
        </div>
      </section>
    </div>
  );
}
