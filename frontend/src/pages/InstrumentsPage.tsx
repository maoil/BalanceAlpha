import { FormEvent, useState } from "react";
import { Clock3, Pencil, Power, RefreshCw } from "lucide-react";

import { api } from "../api/endpoints";
import { DataState, Notice } from "../components/DataState";
import { useAsyncData, useMutationStatus } from "../hooks";
import type { Instrument } from "../types";

export function InstrumentsPage() {
  const [status, setStatus] = useState("");
  const [accountType, setAccountType] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingInstrument, setEditingInstrument] = useState<Instrument | null>(null);
  const instruments = useAsyncData(
    () => api.instruments({ status, account_type: accountType }),
    [status, accountType]
  );
  const backtestConfigs = useAsyncData(() => api.backtestConfigs(), []);
  const mutation = useMutationStatus();

  async function createInstrument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    await mutation.run(async () => {
      await api.createInstrument({
        symbol: String(form.get("symbol") || "").trim(),
        ...instrumentFormPayload(form),
      });
      await instruments.reload();
      setShowCreateForm(false);
      formElement.reset();
    }, "产品已创建");
  }

  async function updateInstrument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingInstrument) {
      return;
    }
    const form = new FormData(event.currentTarget);
    await mutation.run(async () => {
      await api.updateInstrument(editingInstrument.id, instrumentFormPayload(form));
      await instruments.reload();
      setEditingInstrument(null);
    }, "产品已更新");
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>产品管理</h1>
          <p>维护基金、ETF、LOF 基础信息，并触发行情抓取。</p>
        </div>
        <div className="button-row">
          <button
            className="primary-button"
            type="button"
            onClick={() => setShowCreateForm(true)}
          >
            新增产品
          </button>
          <button
            className="ghost-button"
            type="button"
            disabled={mutation.busy}
            onClick={() =>
              mutation.run(async () => {
                await api.fetchAllPrices();
                await instruments.reload();
              }, "全部价格已刷新")
            }
          >
            批量更新价格
          </button>
        </div>
      </div>

      <Notice message={mutation.message} />
      <Notice message={mutation.error} tone="error" />

      <section className="toolbar">
        <label>
          状态
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">全部</option>
            <option value="active">启用</option>
            <option value="disabled">停用</option>
          </select>
        </label>
        <label>
          默认账户
          <select
            value={accountType}
            onChange={(event) => setAccountType(event.target.value)}
          >
            <option value="">全部</option>
            <option value="core">核心</option>
            <option value="tactical">战术</option>
          </select>
        </label>
      </section>

      {showCreateForm && (
      <div className="modal-backdrop" onClick={() => setShowCreateForm(false)}>
        <div
          aria-labelledby="create-instrument-title"
          aria-modal="true"
          className="modal-dialog small-modal"
          role="dialog"
          onClick={(event) => event.stopPropagation()}
        >
          <form onSubmit={createInstrument}>
            <div className="panel-header">
              <h2 id="create-instrument-title">新增产品</h2>
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
                代码
                <input name="symbol" required />
              </label>
              <label>
                名称
                <input name="name" required />
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
                交易模式
                <select name="trade_mode" defaultValue="exchange_traded">
                  <option value="exchange_traded">场内</option>
                  <option value="eod_nav">净值确认</option>
                </select>
              </label>
              <label>
                默认账户
                <select name="default_account_type" defaultValue="core">
                  <option value="core">核心</option>
                  <option value="tactical">战术</option>
                </select>
              </label>
              <label className="check-label">
                <input name="is_dca_eligible" type="checkbox" />
                支持定投
              </label>
              <label>
                确认周期
                <select name="dca_confirm_cycle" defaultValue="1">
                  <option value="0">T+0</option>
                  <option value="1">T+1</option>
                  <option value="2">T+2</option>
                </select>
              </label>
              <label>
                绑定策略
                <select name="backtest_config_key" defaultValue="">
                  <option value="">不绑定</option>
                  {backtestConfigs.data?.map((config) => (
                    <option key={config.key} value={config.key}>
                      {config.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                追踪指数
                <input name="tracking_index" placeholder="如 000977.SH" />
              </label>
            </div>
            <button className="primary-button" disabled={mutation.busy} type="submit">
              创建
            </button>
          </form>
        </div>
      </div>
      )}

      {editingInstrument && (
      <div
        className="modal-backdrop"
        onClick={() => setEditingInstrument(null)}
      >
        <div
          aria-labelledby="edit-instrument-title"
          aria-modal="true"
          className="modal-dialog"
          role="dialog"
          onClick={(event) => event.stopPropagation()}
        >
          <form key={editingInstrument.id} onSubmit={updateInstrument}>
            <div className="panel-header">
              <h2 id="edit-instrument-title">修改产品</h2>
              <button
                className="ghost-button"
                type="button"
                onClick={() => setEditingInstrument(null)}
              >
                取消
              </button>
            </div>
            <div className="form-grid">
              <label>
                修改代码
                <input readOnly value={editingInstrument.symbol} />
              </label>
              <label>
                修改名称
                <input name="name" defaultValue={editingInstrument.name} required />
              </label>
              <label>
                修改类型
                <select
                  name="instrument_type"
                  defaultValue={editingInstrument.instrument_type}
                >
                  <option value="etf">ETF</option>
                  <option value="lof">LOF</option>
                  <option value="fund">基金</option>
                </select>
              </label>
              <label>
                修改交易模式
                <select
                  name="trade_mode"
                  defaultValue={editingInstrument.trade_mode || "eod_nav"}
                >
                  <option value="exchange_traded">场内</option>
                  <option value="eod_nav">净值确认</option>
                </select>
              </label>
              <label>
                修改默认账户
                <select
                  name="default_account_type"
                  defaultValue={editingInstrument.default_account_type || "core"}
                >
                  <option value="core">核心</option>
                  <option value="tactical">战术</option>
                </select>
              </label>
              <label>
                确认周期
                <select
                  name="dca_confirm_cycle"
                  defaultValue={String(editingInstrument.dca_confirm_cycle ?? 1)}
                >
                  <option value="0">T+0</option>
                  <option value="1">T+1</option>
                  <option value="2">T+2</option>
                </select>
              </label>
              <label className="check-label">
                <input
                  name="is_dca_eligible"
                  type="checkbox"
                  defaultChecked={editingInstrument.is_dca_eligible}
                />
                支持定投
              </label>
              <label>
                修改备注
                <input name="notes" defaultValue={editingInstrument.notes || ""} />
              </label>
              <label>
                绑定策略
                <select
                  name="backtest_config_key"
                  defaultValue={editingInstrument.backtest_config_key || ""}
                >
                  <option value="">不绑定</option>
                  {backtestConfigs.data?.map((config) => (
                    <option key={config.key} value={config.key}>
                      {config.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                追踪指数
                <input
                  name="tracking_index"
                  defaultValue={editingInstrument.tracking_index || ""}
                  placeholder="如 000977.SH"
                />
              </label>
            </div>
            <button className="primary-button" disabled={mutation.busy} type="submit">
              保存产品
            </button>
          </form>
        </div>
      </div>
      )}

      <section className="panel">
        <div className="panel-header">
          <h2>产品列表</h2>
          <span>{instruments.data?.length || 0} 条</span>
        </div>
        <DataState loading={instruments.loading} error={instruments.error}>
          <table className="data-table">
            <thead>
              <tr>
                <th>代码</th>
                <th>名称</th>
                <th>类型</th>
                <th>账户</th>
                <th>模式</th>
                <th>确认</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {instruments.data?.map((instrument) => (
                <tr key={instrument.id}>
                  <td>{instrument.symbol}</td>
                  <td>{instrument.name}</td>
                  <td>
                    <span className={`type-badge ${instrument.instrument_type}`}>
                      {instrumentTypeLabel(instrument.instrument_type)}
                    </span>
                  </td>
                  <td>{accountTypeLabel(instrument.default_account_type)}</td>
                  <td>{tradeModeLabel(instrument.trade_mode)}</td>
                  <td>T+{instrument.dca_confirm_cycle ?? 1}</td>
                  <td>
                    <span className={`status-pill ${instrument.status}`}>
                      {instrument.status}
                    </span>
                  </td>
                  <td className="action-row">
                    <button
                      aria-label="刷新价格"
                      className="action-button"
                      title="刷新价格"
                      type="button"
                      onClick={() =>
                        mutation.run(async () => {
                          await api.fetchInstrumentPrice(instrument.id);
                          await instruments.reload();
                        }, "价格已刷新")
                      }
                    >
                      <RefreshCw aria-hidden="true" />
                      <span>刷新</span>
                    </button>
                    <button
                      aria-label="导入历史"
                      className="action-button"
                      title="导入历史"
                      type="button"
                      onClick={() =>
                        mutation.run(
                          () => api.fetchInstrumentHistory(instrument.id, 90),
                          "历史行情已导入"
                        )
                      }
                    >
                      <Clock3 aria-hidden="true" />
                      <span>历史</span>
                    </button>
                    <button
                      aria-label={instrument.status === "active" ? "停用产品" : "启用产品"}
                      className="action-button"
                      title={instrument.status === "active" ? "停用产品" : "启用产品"}
                      type="button"
                      onClick={() =>
                        mutation.run(async () => {
                          await api.updateInstrumentStatus(
                            instrument.id,
                            instrument.status === "active" ? "disabled" : "active"
                          );
                          await instruments.reload();
                        }, "状态已更新")
                      }
                    >
                      <Power aria-hidden="true" />
                      <span>{instrument.status === "active" ? "停用" : "启用"}</span>
                    </button>
                    <button
                      aria-label="修改产品"
                      className="action-button primary-action"
                      title="修改产品"
                      type="button"
                      onClick={() => {
                        setShowCreateForm(false);
                        setEditingInstrument(instrument);
                      }}
                    >
                      <Pencil aria-hidden="true" />
                      <span>修改</span>
                    </button>
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

function instrumentFormPayload(form: FormData) {
  return {
    name: String(form.get("name") || "").trim(),
    instrument_type: String(form.get("instrument_type") || "fund"),
    trade_mode: String(form.get("trade_mode") || "eod_nav"),
    default_account_type: String(form.get("default_account_type") || "core"),
    is_dca_eligible: form.get("is_dca_eligible") === "on",
    dca_confirm_cycle: Number(form.get("dca_confirm_cycle") || 1),
    notes: String(form.get("notes") || ""),
    backtest_config_key: String(form.get("backtest_config_key") || ""),
    tracking_index: String(form.get("tracking_index") || ""),
  };
}

function instrumentTypeLabel(value?: string | null) {
  const labels: Record<string, string> = {
    etf: "ETF",
    lof: "LOF",
    fund: "基金",
  };
  return labels[value || ""] || value || "-";
}

function accountTypeLabel(value?: string | null) {
  const labels: Record<string, string> = {
    core: "核心",
    tactical: "战术",
  };
  return labels[value || ""] || value || "-";
}

function tradeModeLabel(value?: string | null) {
  const labels: Record<string, string> = {
    exchange_traded: "场内",
    eod_nav: "场外",
  };
  return labels[value || ""] || value || "-";
}
