import { useState } from "react";

import { api } from "../api/endpoints";
import { DataState } from "../components/DataState";
import { useAsyncData } from "../hooks";
import { compactJson, formatDate } from "../utils/format";

export function LogsPage() {
  const [logType, setLogType] = useState("");
  const [level, setLevel] = useState("");
  const [selected, setSelected] = useState<unknown>(null);
  const logs = useAsyncData(
    () => api.logs({ log_type: logType || undefined, level: level || undefined, limit: 200 }),
    [logType, level]
  );
  const vix = useAsyncData(() => api.vixHistory(30, "daily"), []);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>系统日志</h1>
          <p>查看参数变更、信号生成和运行时事件，并监控 VIX 历史数据。</p>
        </div>
      </div>

      <section className="toolbar">
        <label>
          类型
          <select value={logType} onChange={(event) => setLogType(event.target.value)}>
            <option value="">全部</option>
            <option value="param_change">参数变更</option>
            <option value="signal">信号</option>
          </select>
        </label>
        <label>
          等级
          <select value={level} onChange={(event) => setLevel(event.target.value)}>
            <option value="">全部</option>
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="error">error</option>
          </select>
        </label>
      </section>

      <section className="content-grid">
        <div className="panel wide">
          <div className="panel-header">
            <h2>日志列表</h2>
            <span>{logs.data?.length || 0} 条</span>
          </div>
          <DataState loading={logs.loading} error={logs.error}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>类型</th>
                  <th>等级</th>
                  <th>模块</th>
                  <th>消息</th>
                </tr>
              </thead>
              <tbody>
                {logs.data?.map((log) => (
                  <tr key={log.id} onClick={() => setSelected(log.context)}>
                    <td>{formatDate(log.created_at)}</td>
                    <td>{log.log_type}</td>
                    <td>{log.level}</td>
                    <td>{log.module}</td>
                    <td>{log.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </DataState>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2>上下文</h2>
          </div>
          <pre className="json-block">{compactJson(selected)}</pre>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2>VIX 数据</h2>
            <span>{vix.data?.source || "daily"}</span>
          </div>
          <DataState loading={vix.loading} error={vix.error}>
            <pre className="json-block">{compactJson(vix.data?.series?.slice(0, 8))}</pre>
          </DataState>
        </div>
      </section>
    </div>
  );
}
