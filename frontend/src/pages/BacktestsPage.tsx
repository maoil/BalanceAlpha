import { FormEvent, useState } from "react";

import { api } from "../api/endpoints";
import { DateField } from "../components/DateField";
import { DataState, Notice } from "../components/DataState";
import { useAsyncData, useMutationStatus } from "../hooks";
import { compactJson, formatDate } from "../utils/format";
import type { BacktestRun } from "../types";

export function BacktestsPage() {
  const [selected, setSelected] = useState<BacktestRun | null>(null);
  const accounts = useAsyncData(() => api.accounts(), []);
  const instruments = useAsyncData(() => api.instruments({ status: "active" }), []);
  const templates = useAsyncData(() => api.strategyTemplates(), []);
  const runs = useAsyncData(() => api.backtests(100), []);
  const mutation = useMutationStatus();

  async function createBacktest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await mutation.run(async () => {
      const created = await api.createBacktest({
        run_name: String(form.get("run_name") || ""),
        account_id: Number(form.get("account_id")),
        instrument_id: optionalNumber(form.get("instrument_id")),
        template_id: optionalNumber(form.get("template_id")),
        start_date: String(form.get("start_date")),
        end_date: String(form.get("end_date")),
        initial_capital: Number(form.get("initial_capital") || 100000),
        fee_rate: Number(form.get("fee_rate") || 0.001),
      });
      setSelected(created);
      await runs.reload();
      event.currentTarget.reset();
    }, "回测已完成");
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>策略回测</h1>
          <p>按账户、产品或模板运行回测，并查看结果摘要。</p>
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
              账户
              <select name="account_id" required>
                <option value="">选择账户</option>
                {accounts.data?.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.account_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              产品
              <select name="instrument_id">
                <option value="">全部</option>
                {instruments.data?.map((instrument) => (
                  <option key={instrument.id} value={instrument.id}>
                    {instrument.symbol} {instrument.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              模板
              <select name="template_id">
                <option value="">默认</option>
                {templates.data?.map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.template_name}
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
              费率
              <input name="fee_rate" defaultValue="0.001" min="0" step="0.0001" type="number" />
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
          <pre className="json-block">{compactJson(selected?.summary || selected?.result)}</pre>
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
                <th>区间</th>
                <th>模板</th>
                <th>状态</th>
                <th>创建时间</th>
              </tr>
            </thead>
            <tbody>
              {runs.data?.map((run) => (
                <tr key={run.id} onClick={() => setSelected(run)}>
                  <td>{run.run_name}</td>
                  <td>
                    {formatDate(run.start_date)} 至 {formatDate(run.end_date)}
                  </td>
                  <td>{run.template?.template_name || run.template_id || "-"}</td>
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

function optionalNumber(value: FormDataEntryValue | null) {
  if (value === null || value === "") {
    return undefined;
  }
  return Number(value);
}
