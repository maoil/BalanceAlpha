import { FormEvent, useEffect, useState } from "react";

import { api } from "../api/endpoints";
import { DateField } from "../components/DateField";
import { DataState, Notice } from "../components/DataState";
import { useAsyncData, useMutationStatus } from "../hooks";
import { formatDate, formatNumber } from "../utils/format";

export function TradesPage() {
  const [accountId, setAccountId] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createAccountId, setCreateAccountId] = useState("");
  const [createInstrumentId, setCreateInstrumentId] = useState("");
  const [createTradeType, setCreateTradeType] = useState("buy");
  const accounts = useAsyncData(() => api.accounts(), []);
  const instruments = useAsyncData(() => api.instruments({ status: "active" }), []);
  const trades = useAsyncData(
    () => api.trades({ account_id: accountId || undefined, limit: 200 }),
    [accountId]
  );
  const mutation = useMutationStatus();
  const selectedCreateInstrument = instruments.data?.find(
    (item) => String(item.id) === createInstrumentId
  );
  const isFundBuyTrade =
    selectedCreateInstrument?.instrument_type === "fund" && createTradeType === "buy";
  const isFundSellTrade =
    selectedCreateInstrument?.instrument_type === "fund" && createTradeType === "sell";

  useEffect(() => {
    if (!createInstrumentId) {
      setCreateAccountId("");
      return;
    }
    const instrument = instruments.data?.find(
      (item) => String(item.id) === createInstrumentId
    );
    if (!instrument?.default_account_type) {
      return;
    }
    const mappedAccount = accounts.data?.find(
      (account) => account.account_type === instrument.default_account_type
    );
    if (mappedAccount) {
      setCreateAccountId(String(mappedAccount.id));
    }
  }, [accounts.data, createInstrumentId, instruments.data]);

  function openCreateForm() {
    setCreateAccountId("");
    setCreateInstrumentId("");
    setCreateTradeType("buy");
    setShowCreateForm(true);
  }

  function closeCreateForm() {
    setCreateAccountId("");
    setCreateInstrumentId("");
    setCreateTradeType("buy");
    setShowCreateForm(false);
  }

  async function createTrade(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    await mutation.run(async () => {
      await api.createTrade({
        account_id: Number(form.get("account_id")),
        instrument_id: Number(form.get("instrument_id")),
        trade_date: String(form.get("trade_date")),
        trade_type: String(form.get("trade_type")),
        quantity: optionalNumber(form.get("quantity")),
        price: optionalNumber(form.get("price")),
        amount: optionalNumber(form.get("amount")),
        fee: optionalNumber(form.get("fee")) || 0,
        reason_code: String(form.get("reason_code") || ""),
        notes: String(form.get("notes") || ""),
      });
      await trades.reload();
      formElement.reset();
      closeCreateForm();
    }, "交易已提交");
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>交易记录</h1>
          <p>录入买入、卖出、申购和赎回，场外基金会进入确认流程。</p>
        </div>
        <button
          className="primary-button"
          type="button"
          onClick={openCreateForm}
        >
          新增交易
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
      </section>

      {showCreateForm && (
      <div className="modal-backdrop" onClick={closeCreateForm}>
        <div
          aria-labelledby="create-trade-title"
          aria-modal="true"
          className="modal-dialog small-modal"
          role="dialog"
          onClick={(event) => event.stopPropagation()}
        >
          <form onSubmit={createTrade}>
            <div className="panel-header">
              <h2 id="create-trade-title">新增交易</h2>
              <button
                className="ghost-button"
                type="button"
                onClick={closeCreateForm}
              >
                取消
              </button>
            </div>
            <div className="form-grid">
              <label>
                账户
                <select
                  name="account_id"
                  required
                  value={createAccountId}
                  onChange={(event) => setCreateAccountId(event.target.value)}
                >
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
                <select
                  name="instrument_id"
                  required
                  value={createInstrumentId}
                  onChange={(event) => setCreateInstrumentId(event.target.value)}
                >
                  <option value="">选择产品</option>
                  {instruments.data?.map((instrument) => (
                    <option key={instrument.id} value={instrument.id}>
                      {instrument.symbol} {instrument.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                日期
                <DateField name="trade_date" required />
              </label>
              <label>
                类型
                <select
                  name="trade_type"
                  value={createTradeType}
                  onChange={(event) => setCreateTradeType(event.target.value)}
                >
                  <option value="buy">买入</option>
                  <option value="sell">卖出</option>
                  <option value="subscribe">申购</option>
                  <option value="redeem">赎回</option>
                </select>
              </label>
              {!isFundBuyTrade && (
              <label>
                数量
                <input name="quantity" min="0" step="0.0001" type="number" />
              </label>
              )}
              {!isFundBuyTrade && !isFundSellTrade && (
              <label>
                价格
                <input name="price" min="0" step="0.0001" type="number" />
              </label>
              )}
              {!isFundSellTrade && (
              <label>
                金额
                <input name="amount" min="0" step="0.01" type="number" />
              </label>
              )}
              <label>
                手续费
                <input name="fee" min="0" step="0.01" type="number" />
              </label>
              <label>
                原因
                <input name="reason_code" />
              </label>
              <label>
                备注
                <input name="notes" />
              </label>
            </div>
            <button className="primary-button" disabled={mutation.busy} type="submit">
              提交
            </button>
          </form>
        </div>
      </div>
      )}

      <section className="panel">
        <div className="panel-header">
          <h2>交易流水</h2>
          <span>{trades.data?.length || 0} 条</span>
        </div>
        <DataState loading={trades.loading} error={trades.error}>
          <table className="data-table">
            <thead>
              <tr>
                <th>下单/确认日</th>
                <th>账户</th>
                <th>产品</th>
                <th>类型</th>
                <th>数量</th>
                <th>成交价/净值</th>
                <th>金额</th>
              </tr>
            </thead>
            <tbody>
              {trades.data?.map((trade) => {
                const sourceOrder = trade.source_order;
                const confirmDate =
                  sourceOrder?.actual_confirm_date ||
                  sourceOrder?.quote_date_used ||
                  trade.trade_date;

                return (
                  <tr key={trade.id}>
                    <td>
                      {sourceOrder?.order_date ? (
                        <div className="stacked-cell">
                          <strong>下单 {formatDate(sourceOrder.order_date)}</strong>
                          <span>确认 {formatDate(confirmDate)}</span>
                        </div>
                      ) : (
                        formatDate(trade.trade_date)
                      )}
                    </td>
                    <td>{trade.account?.account_name || trade.account_id}</td>
                    <td>{trade.instrument?.symbol || trade.instrument_id}</td>
                    <td>{trade.trade_type}</td>
                    <td>{formatNumber(trade.quantity, 4)}</td>
                    <td>
                      {sourceOrder ? (
                        <div className="stacked-cell">
                          <strong>{formatNumber(trade.price, 4)}</strong>
                          <span>交易日净值</span>
                        </div>
                      ) : (
                        formatNumber(trade.price, 4)
                      )}
                    </td>
                    <td>{formatNumber(trade.amount)}</td>
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

function optionalNumber(value: FormDataEntryValue | null) {
  if (value === null || value === "") {
    return undefined;
  }
  return Number(value);
}
