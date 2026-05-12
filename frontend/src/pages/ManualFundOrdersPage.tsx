import { useState } from "react";

import { api } from "../api/endpoints";
import { DataState, Notice } from "../components/DataState";
import { useAsyncData, useMutationStatus } from "../hooks";
import { formatDate, formatNumber } from "../utils/format";

export function ManualFundOrdersPage() {
  const [status, setStatus] = useState("pending");
  const orders = useAsyncData(
    () => api.manualFundOrders({ status: status || undefined, limit: 200 }),
    [status]
  );
  const mutation = useMutationStatus();
  const visibleOrders = orders.data || [];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>基金确认</h1>
          <p>处理净值确认型基金的待确认申购和赎回。</p>
        </div>
      </div>

      <Notice message={mutation.message} />
      <Notice message={mutation.error} tone="error" />

      <section className="toolbar">
        <label>
          状态
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">全部</option>
            <option value="pending">待确认</option>
            <option value="confirmed">已确认</option>
            <option value="cancelled">已撤回</option>
            <option value="failed">失败</option>
          </select>
        </label>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>确认单</h2>
          <span>{visibleOrders.length} 条</span>
        </div>
        <DataState loading={orders.loading} error={orders.error}>
          <table className="data-table">
            <thead>
              <tr>
                <th>下单日</th>
                <th>预计确认</th>
                <th>账户</th>
                <th>产品</th>
                <th>方向</th>
                <th>金额/份额</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {visibleOrders.map((order) => (
                <tr key={order.id}>
                  <td>{formatDate(order.order_date)}</td>
                  <td>{formatDate(order.expected_confirm_date)}</td>
                  <td>{order.account?.account_name || order.account_id}</td>
                  <td>{order.instrument?.symbol || order.instrument_id}</td>
                  <td>{order.side}</td>
                  <td>
                    {order.amount ? formatNumber(order.amount) : formatNumber(order.quantity, 4)}
                  </td>
                  <td>
                    <span className={`status-pill ${order.status}`}>{order.status}</span>
                  </td>
                  <td>
                    {order.status === "pending" && (
                    <>
                      <button
                        className="ghost-button small"
                        disabled={mutation.busy}
                        type="button"
                        onClick={() =>
                          mutation.run(async () => {
                            await api.confirmManualFundOrder(order.id);
                            await orders.reload();
                          }, "确认完成")
                        }
                      >
                        确认
                      </button>
                      <button
                        className="ghost-button small danger"
                        disabled={mutation.busy}
                        type="button"
                        onClick={() => {
                          if (!confirm("确认撤回该确认单？")) return;
                          mutation.run(async () => {
                            await api.revokeManualFundOrder(order.id);
                            await orders.reload();
                          }, "已撤回");
                        }}
                      >
                        撤回
                      </button>
                    </>
                    )}
                    {order.status === "confirmed" && (
                      <button
                        className="ghost-button small danger"
                        disabled={mutation.busy}
                        type="button"
                        onClick={() => {
                          if (!confirm("确认撤回该确认单？关联交易将被删除，持仓将同步回退。")) return;
                          mutation.run(async () => {
                            await api.revokeManualFundOrder(order.id);
                            await orders.reload();
                          }, "已撤回");
                        }}
                      >
                        撤回
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </DataState>
      </section>
    </div>
  );
}
