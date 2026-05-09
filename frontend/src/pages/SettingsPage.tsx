import { FormEvent, useMemo, useState } from "react";

import { api } from "../api/endpoints";
import { DataState, Notice } from "../components/DataState";
import { useAsyncData, useMutationStatus } from "../hooks";
import { compactJson, formatPercent } from "../utils/format";

export function SettingsPage() {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const templates = useAsyncData(() => api.strategyTemplates(), []);
  const performance = useAsyncData(() => api.strategyPerformance(7), []);
  const mutation = useMutationStatus();
  const selected = useMemo(
    () => templates.data?.find((template) => template.id === selectedId) || templates.data?.[0],
    [templates.data, selectedId]
  );

  async function saveTemplate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) {
      return;
    }
    const form = new FormData(event.currentTarget);
    const configText = String(form.get("config") || "{}");
    await mutation.run(async () => {
      await api.updateStrategyTemplate(selected.id, {
        template_name: String(form.get("template_name")),
        description: String(form.get("description") || ""),
        config: JSON.parse(configText),
      });
      await templates.reload();
    }, "参数模板已保存");
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>参数配置</h1>
          <p>维护策略模板 JSON 参数，并查看最近策略表现。</p>
        </div>
      </div>

      <Notice message={mutation.message} />
      <Notice message={mutation.error} tone="error" />

      <section className="content-grid">
        <div className="panel">
          <div className="panel-header">
            <h2>模板列表</h2>
            <span>{templates.data?.length || 0} 个</span>
          </div>
          <DataState loading={templates.loading} error={templates.error}>
            <div className="template-list">
              {templates.data?.map((template) => (
                <button
                  className={
                    template.id === selected?.id ? "template-item active" : "template-item"
                  }
                  key={template.id}
                  type="button"
                  onClick={() => setSelectedId(template.id)}
                >
                  <strong>{template.template_name}</strong>
                  <span>
                    {template.account_type} · v{template.version}
                  </span>
                </button>
              ))}
            </div>
          </DataState>
        </div>

        <form className="panel form-panel wide" onSubmit={saveTemplate}>
          <div className="panel-header">
            <h2>编辑模板</h2>
            <span>{selected?.template_code}</span>
          </div>
          {selected && (
            <>
              <div className="form-grid">
                <label>
                  名称
                  <input name="template_name" defaultValue={selected.template_name} />
                </label>
                <label>
                  描述
                  <input name="description" defaultValue={selected.description || ""} />
                </label>
              </div>
              <label className="stack-label">
                JSON 配置
                <textarea
                  name="config"
                  defaultValue={JSON.stringify(selected.config, null, 2)}
                  rows={16}
                />
              </label>
              <button className="primary-button" disabled={mutation.busy} type="submit">
                保存模板
              </button>
            </>
          )}
        </form>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>策略表现</h2>
          <span>近 7 日</span>
        </div>
        <DataState loading={performance.loading} error={performance.error}>
          <table className="data-table">
            <thead>
              <tr>
                <th>策略</th>
                <th>收益</th>
                <th>胜率</th>
                <th>最大回撤</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {performance.data?.map((item) => (
                <tr key={item.strategy_name}>
                  <td>{item.strategy_name}</td>
                  <td>{formatPercent(item.return_7d)}</td>
                  <td>{formatPercent(item.win_rate)}</td>
                  <td>{formatPercent(item.max_drawdown)}</td>
                  <td>{item.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataState>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>当前模板结构</h2>
        </div>
        <pre className="json-block">{compactJson(selected?.config)}</pre>
      </section>
    </div>
  );
}
