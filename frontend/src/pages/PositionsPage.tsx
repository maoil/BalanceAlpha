import { FormEvent, useState } from "react";

import { api } from "../api/endpoints";
import { DataState, Notice } from "../components/DataState";
import { useAsyncData, useMutationStatus } from "../hooks";
import { formatNumber, formatPercent, formatSignedNumber, valueTone } from "../utils/format";
import type { Position } from "../types";

type PositionDraft = {
  quantity: string;
  avg_cost: string;
  market_price: string;
};

export function PositionsPage() {
  const [accountId, setAccountId] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingPositionId, setEditingPositionId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState<PositionDraft | null>(null);
  const accounts = useAsyncData(() => api.accounts(), []);
  const positions = useAsyncData(
    () => api.positions({ account_id: accountId || undefined }),
    [accountId]
  );
  const mutation = useMutationStatus();

  async function createPosition(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    await mutation.run(async () => {
      await api.createPosition({
        account_id: Number(form.get("account_id")),
        symbol: String(form.get("symbol")),
        name: String(form.get("name") || form.get("symbol")),
        instrument_type: String(form.get("instrument_type")),
        quantity: Number(form.get("quantity")),
        market_price: Number(form.get("market_price")),
        unrealized_pnl: Number(form.get("unrealized_pnl") || 0),
      });
      await positions.reload();
      setShowCreateForm(false);
      formElement.reset();
    }, "持仓已创建");
  }

  function startEdit(position: Position) {
    setEditingPositionId(position.id);
    setEditDraft({
      quantity: String(position.quantity ?? ""),
      avg_cost: String(position.avg_cost ?? ""),
      market_price: String(position.market_price ?? ""),
    });
  }

  function updateDraft(field: keyof PositionDraft, value: string) {
    setEditDraft((current) => (current ? { ...current, [field]: value } : current));
  }

  async function savePosition(positionId: number) {
    if (!editDraft) {
      return;
    }
    await mutation.run(async () => {
      await api.updatePosition(positionId, {
        quantity: Number(editDraft.quantity),
        avg_cost: Number(editDraft.avg_cost),
        market_price: Number(editDraft.market_price),
      });
      await positions.reload();
      setEditingPositionId(null);
      setEditDraft(null);
    }, "持仓已修改");
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>持仓管理</h1>
          <p>查看持仓市值、盈亏与账户权重，并支持手工修正。</p>
        </div>
        <div className="button-row">
          <button
            className="primary-button"
            type="button"
            onClick={() => setShowCreateForm(true)}
          >
            手工新增持仓
          </button>
          <button
            className="ghost-button"
            disabled={mutation.busy}
            type="button"
            onClick={() =>
              mutation.run(async () => {
                await api.refreshPositionPrices();
                await positions.reload();
              }, "价格已按本地行情刷新")
            }
          >
            刷新本地价
          </button>
          <button
            className="primary-button"
            disabled={mutation.busy}
            type="button"
            onClick={() =>
              mutation.run(async () => {
                await api.refreshPositions();
                await positions.reload();
              }, "持仓与待确认基金已刷新")
            }
          >
            全量刷新
          </button>
        </div>
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
      </section>

      {showCreateForm && (
      <div className="modal-backdrop" onClick={() => setShowCreateForm(false)}>
        <div
          aria-labelledby="create-position-title"
          aria-modal="true"
          className="modal-dialog small-modal"
          role="dialog"
          onClick={(event) => event.stopPropagation()}
        >
          <form onSubmit={createPosition}>
            <div className="panel-header">
              <h2 id="create-position-title">手工新增持仓</h2>
              <button
                className="ghost-button"
                type="button"
                onClick={() => setShowCreateForm(false)}
              >
                取消
              </button>
            </div>
            <div className="form-grid">
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
                产品代码
                <input name="symbol" required />
              </label>
              <label>
                产品名称
                <input name="name" />
              </label>
              <label>
                类型
                <select name="instrument_type" defaultValue="etf">
                  <option value="etf">ETF</option>
                  <option value="lof">LOF</option>
                  <option value="fund">基金</option>
                </select>
              </label>
              <label>
                数量
                <input name="quantity" min="0" step="0.0001" type="number" required />
              </label>
              <label>
                市价
                <input name="market_price" min="0" step="0.0001" type="number" required />
              </label>
              <label>
                浮盈
                <input name="unrealized_pnl" step="0.01" type="number" />
              </label>
            </div>
            <button className="primary-button" disabled={mutation.busy} type="submit">
              新增
            </button>
          </form>
        </div>
      </div>
      )}

      <section className="panel">
        <div className="panel-header">
          <h2>当前持仓</h2>
          <span>{positions.data?.length || 0} 条</span>
        </div>
        <DataState loading={positions.loading} error={positions.error}>
          <table className="data-table">
            <thead>
              <tr>
                <th>账户</th>
                <th>产品名称</th>
                <th>市值</th>
                <th>盈亏</th>
                <th>权重</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {positions.data?.map((position) => {
                const isEditing = editingPositionId === position.id && editDraft;
                return (
                  <tr key={position.id}>
                    <td>{position.account?.account_name || position.account_id}</td>
                    <td>
                      <div className="stacked-cell">
                        <strong>
                          {position.instrument?.name ||
                            position.instrument?.symbol ||
                            position.instrument_id}
                        </strong>
                        {position.instrument?.symbol && (
                          <span>{position.instrument.symbol}</span>
                        )}
                      </div>
                    </td>
                    <td>{formatNumber(position.market_value)}</td>
                    <td className={`pnl-cell ${valueTone(position.unrealized_pnl)}`}>
                      {formatSignedNumber(position.unrealized_pnl)}
                    </td>
                    <td>{formatPercent(position.weight_in_account)}</td>
                    <td className="action-row">
                      {isEditing ? (
                        <>
                          <label className="compact-field">
                            修改数量
                            <input
                              min="0"
                              step="0.0001"
                              type="number"
                              value={editDraft.quantity}
                              onChange={(event) =>
                                updateDraft("quantity", event.target.value)
                              }
                            />
                          </label>
                          <label className="compact-field">
                            修改成本
                            <input
                              min="0"
                              step="0.0001"
                              type="number"
                              value={editDraft.avg_cost}
                              onChange={(event) =>
                                updateDraft("avg_cost", event.target.value)
                              }
                            />
                          </label>
                          <label className="compact-field">
                            修改市价
                            <input
                              min="0"
                              step="0.0001"
                              type="number"
                              value={editDraft.market_price}
                              onChange={(event) =>
                                updateDraft("market_price", event.target.value)
                              }
                            />
                          </label>
                          <button
                            className="ghost-button small"
                            disabled={mutation.busy}
                            type="button"
                            onClick={() => void savePosition(position.id)}
                          >
                            保存修改
                          </button>
                          <button
                            className="ghost-button small"
                            type="button"
                            onClick={() => {
                              setEditingPositionId(null);
                              setEditDraft(null);
                            }}
                          >
                            取消
                          </button>
                        </>
                      ) : (
                        <button
                          className="ghost-button small"
                          type="button"
                          onClick={() => startEdit(position)}
                        >
                          修改持仓
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </DataState>
      </section>
    </div>
  );
}
