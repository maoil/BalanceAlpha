import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/endpoints";
import { InstrumentsPage } from "./InstrumentsPage";
import { PositionsPage } from "./PositionsPage";
import { TradesPage } from "./TradesPage";

const mockApi = vi.hoisted(() => ({
  accounts: vi.fn(),
  instruments: vi.fn(),
  positions: vi.fn(),
  trades: vi.fn(),
  createInstrument: vi.fn(),
  updateInstrument: vi.fn(),
  createPosition: vi.fn(),
  updatePosition: vi.fn(),
  createTrade: vi.fn(),
  fetchAllPrices: vi.fn(),
  fetchInstrumentPrice: vi.fn(),
  fetchInstrumentHistory: vi.fn(),
  searchFund: vi.fn(),
  updateInstrumentStatus: vi.fn(),
}));

vi.mock("../api/endpoints", () => ({
  api: mockApi,
}));

describe("create form buttons", () => {
  beforeEach(() => {
    mockApi.accounts.mockResolvedValue([
      {
        id: 1,
        account_code: "core",
        account_name: "核心账户",
        account_type: "core",
        status: "active",
      },
    ]);
    mockApi.instruments.mockResolvedValue([]);
    mockApi.positions.mockResolvedValue([]);
    mockApi.trades.mockResolvedValue([]);
    mockApi.createInstrument.mockResolvedValue({});
    mockApi.updateInstrument.mockResolvedValue({});
    mockApi.createPosition.mockResolvedValue({});
    mockApi.updatePosition.mockResolvedValue({});
    mockApi.createTrade.mockResolvedValue({});
    mockApi.fetchAllPrices.mockResolvedValue({});
    mockApi.fetchInstrumentPrice.mockResolvedValue({});
    mockApi.fetchInstrumentHistory.mockResolvedValue({});
    mockApi.searchFund.mockResolvedValue([]);
    mockApi.updateInstrumentStatus.mockResolvedValue({});
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("opens the new instrument form in a small dialog after clicking the add button", async () => {
    const user = userEvent.setup();
    render(<InstrumentsPage />);

    expect(screen.queryByLabelText("代码")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "新增产品" }));

    expect(screen.getByRole("dialog", { name: "新增产品" })).toHaveClass("small-modal");
    expect(screen.getByLabelText("代码")).toBeInTheDocument();
    expect(screen.getByLabelText("名称")).toBeInTheDocument();
  });

  it("updates an existing instrument through the instrument edit form", async () => {
    const user = userEvent.setup();
    vi.mocked(api.instruments).mockResolvedValue([
      {
        id: 11,
        symbol: "007721",
        name: "天弘标普500(QDII-FOF)A",
        instrument_type: "fund",
        trade_mode: "eod_nav",
        default_account_type: "core",
        is_dca_eligible: false,
        dca_confirm_cycle: 1,
        status: "active",
        notes: "",
      },
    ]);

    render(<InstrumentsPage />);

    expect(await screen.findByText("007721")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "刷新价格" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导入历史" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "停用产品" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "修改产品" }));
    expect(screen.getByRole("dialog", { name: "修改产品" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("确认周期"), "2");
    await user.click(screen.getByRole("button", { name: "保存产品" }));

    expect(api.updateInstrument).toHaveBeenCalledWith(11, {
      name: "天弘标普500(QDII-FOF)A",
      instrument_type: "fund",
      trade_mode: "eod_nav",
      default_account_type: "core",
      is_dca_eligible: false,
      dca_confirm_cycle: 2,
      notes: "",
    });
  });

  it("submits zero as the T+0 confirm cycle from the instrument form", async () => {
    const user = userEvent.setup();
    render(<InstrumentsPage />);

    await user.click(screen.getByRole("button", { name: "新增产品" }));
    const dialog = screen.getByRole("dialog", { name: "新增产品" });
    const cycleSelect = dialog.querySelector(
      'select[name="dca_confirm_cycle"]'
    ) as HTMLSelectElement;

    expect(cycleSelect).toBeInTheDocument();
    expect(within(cycleSelect).getByRole("option", { name: "T+0" }))
      .toBeInTheDocument();

    await user.type(
      dialog.querySelector('input[name="symbol"]') as HTMLInputElement,
      "510050"
    );
    await user.type(
      dialog.querySelector('input[name="name"]') as HTMLInputElement,
      "T0 Product"
    );
    await user.selectOptions(cycleSelect, "0");
    await user.click(within(dialog).getByRole("button", { name: "创建" }));

    expect(api.createInstrument).toHaveBeenCalledWith(
      expect.objectContaining({
        symbol: "510050",
        name: "T0 Product",
        dca_confirm_cycle: 0,
      })
    );
  });

  it("maps instrument list codes to Chinese labels and colored type badges", async () => {
    vi.mocked(api.instruments).mockResolvedValue([
      {
        id: 11,
        symbol: "007721",
        name: "天弘标普500(QDII-FOF)A",
        instrument_type: "fund",
        trade_mode: "eod_nav",
        default_account_type: "core",
        is_dca_eligible: false,
        dca_confirm_cycle: 2,
        status: "active",
      },
      {
        id: 12,
        symbol: "510300",
        name: "沪深300ETF",
        instrument_type: "etf",
        trade_mode: "exchange_traded",
        default_account_type: "tactical",
        is_dca_eligible: false,
        dca_confirm_cycle: 1,
        status: "active",
      },
      {
        id: 13,
        symbol: "160706",
        name: "嘉实300LOF",
        instrument_type: "lof",
        trade_mode: "exchange_traded",
        default_account_type: "core",
        is_dca_eligible: false,
        dca_confirm_cycle: 1,
        status: "active",
      },
    ]);

    render(<InstrumentsPage />);

    expect(await screen.findByText("基金")).toHaveClass("type-badge", "fund");
    expect(screen.getByText("ETF")).toHaveClass("type-badge", "etf");
    expect(screen.getByText("LOF")).toHaveClass("type-badge", "lof");
    expect(
      screen.getByRole("row", { name: /007721 天弘标普500\(QDII-FOF\)A 基金 核心 场外/ })
    ).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /510300 沪深300ETF ETF 战术 场内/ }))
      .toBeInTheDocument();
    expect(screen.getByRole("row", { name: /160706 嘉实300LOF LOF 核心 场内/ }))
      .toBeInTheDocument();
  });

  it("opens the manual position form in a small dialog after clicking the add button", async () => {
    const user = userEvent.setup();
    render(<PositionsPage />);

    expect(screen.queryByLabelText("产品代码")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "手工新增持仓" }));

    expect(screen.getByRole("dialog", { name: "手工新增持仓" })).toHaveClass("small-modal");
    expect(screen.getByLabelText("产品代码")).toBeInTheDocument();
    expect(screen.getByLabelText("数量")).toBeInTheDocument();
  });

  it("opens the new trade form in a small dialog after clicking the add button", async () => {
    const user = userEvent.setup();
    render(<TradesPage />);

    expect(screen.queryByLabelText("日期")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "新增交易" }));

    expect(screen.getByRole("dialog", { name: "新增交易" })).toHaveClass("small-modal");
    expect(screen.getByLabelText("日期")).toBeInTheDocument();
    expect(screen.getByLabelText("类型")).toBeInTheDocument();
  });

  it("uses the styled date picker component in the new trade dialog", async () => {
    const user = userEvent.setup();
    render(<TradesPage />);

    await user.click(screen.getByRole("button", { name: "新增交易" }));

    const dateInput = screen.getByLabelText("日期");
    expect(dateInput).toHaveAttribute("type", "date");
    expect(dateInput.closest(".date-field")).toBeInTheDocument();
  });

  it("selects the mapped account automatically after choosing a trade product", async () => {
    const user = userEvent.setup();
    vi.mocked(api.accounts).mockResolvedValue([
      {
        id: 1,
        account_code: "core",
        account_name: "核心账户",
        account_type: "core",
        status: "active",
      },
      {
        id: 2,
        account_code: "tactical",
        account_name: "战术账户",
        account_type: "tactical",
        status: "active",
      },
    ]);
    vi.mocked(api.instruments).mockResolvedValue([
      {
        id: 22,
        symbol: "510300",
        name: "沪深300ETF",
        instrument_type: "etf",
        trade_mode: "exchange_traded",
        default_account_type: "tactical",
        is_dca_eligible: false,
        status: "active",
      },
    ]);

    render(<TradesPage />);

    await user.click(screen.getByRole("button", { name: "新增交易" }));
    const dialog = screen.getByRole("dialog", { name: "新增交易" });
    await within(dialog).findByRole("option", { name: "510300 沪深300ETF" });

    await user.selectOptions(within(dialog).getByLabelText("产品"), "22");

    expect(within(dialog).getByLabelText("账户")).toHaveValue("2");
    await user.type(within(dialog).getByLabelText("日期"), "2026-05-08");
    await user.type(within(dialog).getByLabelText("金额"), "250");
    await user.click(within(dialog).getByRole("button", { name: "提交" }));

    expect(api.createTrade).toHaveBeenCalledWith(
      expect.objectContaining({
        account_id: 2,
        instrument_id: 22,
      })
    );
  });

  it("requires quantity price amount and fee for T+0 trades", async () => {
    const user = userEvent.setup();
    vi.mocked(api.instruments).mockResolvedValue([
      {
        id: 25,
        symbol: "161725",
        name: "T0 Product",
        instrument_type: "fund",
        trade_mode: "eod_nav",
        default_account_type: "core",
        is_dca_eligible: false,
        dca_confirm_cycle: 0,
        status: "active",
      },
    ]);

    render(<TradesPage />);

    await user.click(screen.getByRole("button", { name: "新增交易" }));
    const dialog = screen.getByRole("dialog", { name: "新增交易" });
    await within(dialog).findByRole("option", { name: "161725 T0 Product" });
    await user.selectOptions(
      dialog.querySelector('select[name="instrument_id"]') as HTMLSelectElement,
      "25"
    );

    const quantity = dialog.querySelector('input[name="quantity"]');
    const price = dialog.querySelector('input[name="price"]');
    const amount = dialog.querySelector('input[name="amount"]');
    const fee = dialog.querySelector('input[name="fee"]');

    expect(quantity).toBeInTheDocument();
    expect(price).toBeInTheDocument();
    expect(amount).toBeInTheDocument();
    expect(fee).toBeInTheDocument();
    expect(quantity).toBeRequired();
    expect(price).toBeRequired();
    expect(amount).toBeRequired();
    expect(fee).toBeRequired();

    await user.type(
      dialog.querySelector('input[name="trade_date"]') as HTMLInputElement,
      "2026-05-08"
    );
    await user.type(quantity as HTMLInputElement, "100");
    await user.type(price as HTMLInputElement, "2");
    await user.type(amount as HTMLInputElement, "200");
    await user.type(fee as HTMLInputElement, "0");
    await user.click(within(dialog).getByRole("button", { name: "提交" }));

    expect(api.createTrade).toHaveBeenCalledWith(
      expect.objectContaining({
        instrument_id: 25,
        quantity: 100,
        price: 2,
        amount: 200,
        fee: 0,
      })
    );
  });

  it("shows amount inputs for fund buy trades and hides quantity and price", async () => {
    const user = userEvent.setup();
    vi.mocked(api.instruments).mockResolvedValue([
      {
        id: 23,
        symbol: "007721",
        name: "天弘标普500(QDII-FOF)A",
        instrument_type: "fund",
        trade_mode: "eod_nav",
        default_account_type: "core",
        is_dca_eligible: false,
        status: "active",
      },
    ]);

    render(<TradesPage />);

    await user.click(screen.getByRole("button", { name: "新增交易" }));
    const dialog = screen.getByRole("dialog", { name: "新增交易" });
    await within(dialog).findByRole("option", { name: "007721 天弘标普500(QDII-FOF)A" });
    await user.selectOptions(within(dialog).getByLabelText("产品"), "23");

    expect(within(dialog).getByLabelText("金额")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("手续费")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("原因")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("备注")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("数量")).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText("价格")).not.toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("日期"), "2026-05-08");
    await user.type(within(dialog).getByLabelText("金额"), "500");
    await user.click(within(dialog).getByRole("button", { name: "提交" }));

    expect(api.createTrade).toHaveBeenCalledWith(
      expect.objectContaining({
        instrument_id: 23,
        trade_type: "buy",
        amount: 500,
        quantity: undefined,
        price: undefined,
      })
    );
  });

  it("shows quantity inputs for fund sell trades and hides amount and price", async () => {
    const user = userEvent.setup();
    vi.mocked(api.instruments).mockResolvedValue([
      {
        id: 24,
        symbol: "007721",
        name: "天弘标普500(QDII-FOF)A",
        instrument_type: "fund",
        trade_mode: "eod_nav",
        default_account_type: "core",
        is_dca_eligible: false,
        status: "active",
      },
    ]);

    render(<TradesPage />);

    await user.click(screen.getByRole("button", { name: "新增交易" }));
    const dialog = screen.getByRole("dialog", { name: "新增交易" });
    await within(dialog).findByRole("option", { name: "007721 天弘标普500(QDII-FOF)A" });
    await user.selectOptions(within(dialog).getByLabelText("产品"), "24");
    await user.selectOptions(within(dialog).getByLabelText("类型"), "sell");

    expect(within(dialog).getByLabelText("数量")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("手续费")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("原因")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("备注")).toBeInTheDocument();
    expect(within(dialog).queryByLabelText("金额")).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText("价格")).not.toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("日期"), "2026-05-08");
    await user.type(within(dialog).getByLabelText("数量"), "100");
    await user.click(within(dialog).getByRole("button", { name: "提交" }));

    expect(api.createTrade).toHaveBeenCalledWith(
      expect.objectContaining({
        instrument_id: 24,
        trade_type: "sell",
        quantity: 100,
        amount: undefined,
        price: undefined,
      })
    );
  });

  it("submits a new trade without losing the form reset target", async () => {
    const user = userEvent.setup();
    vi.mocked(api.instruments).mockResolvedValue([
      {
        id: 2,
        symbol: "510300",
        name: "沪深300ETF",
        instrument_type: "etf",
        is_dca_eligible: false,
        status: "active",
      },
    ]);

    render(<TradesPage />);

    await user.click(screen.getByRole("button", { name: "新增交易" }));
    await user.selectOptions(screen.getAllByLabelText("账户")[1], "1");
    await user.selectOptions(screen.getByLabelText("产品"), "2");
    await user.type(screen.getByLabelText("日期"), "2026-05-08");
    await user.type(screen.getByLabelText("数量"), "100");
    await user.type(screen.getByLabelText("价格"), "2.5");
    await user.type(screen.getByLabelText("金额"), "250");
    await user.click(screen.getByRole("button", { name: "提交" }));

    expect(await screen.findByText("交易已提交")).toBeInTheDocument();
    expect(screen.queryByText(/Cannot read properties of null/)).not.toBeInTheDocument();
  });

  it("shows manual fund order and confirmation dates in trade history", async () => {
    vi.mocked(api.trades).mockResolvedValue([
      {
        id: 20,
        account_id: 1,
        instrument_id: 2,
        account: {
          id: 1,
          account_code: "core",
          account_name: "核心账户",
          account_type: "core",
          status: "active",
        },
        instrument: {
          id: 2,
          symbol: "161725",
          name: "白酒基金",
          instrument_type: "fund",
          trade_mode: "eod_nav",
          is_dca_eligible: false,
          status: "active",
        },
        trade_date: "2026-05-06",
        trade_type: "subscribe",
        side: "buy",
        quantity: 800,
        price: 1.25,
        amount: 1000,
        fee: 0,
        source_type: "manual_fund_order",
        source_id: 9,
        source_order: {
          id: 9,
          order_date: "2026-04-30",
          expected_confirm_date: "2026-05-06",
          actual_confirm_date: "2026-05-06",
          confirm_nav: 1.25,
          confirm_quantity: 800,
          quote_date_used: "2026-05-06",
          status: "confirmed",
          linked_trade_id: 20,
        },
      },
    ]);

    render(<TradesPage />);

    expect(await screen.findByText("下单 2026-04-30")).toBeInTheDocument();
    expect(screen.getByText("确认 2026-05-06")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "成交价/净值" })).toBeInTheDocument();
    expect(screen.getByText("交易日净值")).toBeInTheDocument();
  });

  it("updates an existing position through the position patch API", async () => {
    const user = userEvent.setup();
    vi.mocked(api.positions).mockResolvedValue([
      {
        id: 7,
        account_id: 1,
        instrument_id: 2,
        account: {
          id: 1,
          account_code: "core",
          account_name: "核心账户",
          account_type: "core",
          status: "active",
        },
        instrument: {
          id: 2,
          symbol: "510300",
          name: "沪深300ETF",
          instrument_type: "etf",
          is_dca_eligible: false,
          status: "active",
        },
        quantity: 100,
        avg_cost: 2.1,
        market_price: 2.6,
        market_value: 260,
        unrealized_pnl: 50,
        unrealized_pnl_pct: 0.2381,
        weight_in_account: 0.2,
        position_status: "open",
      },
    ]);

    render(<PositionsPage />);

    expect(await screen.findByText("510300")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "修改持仓" }));
    await user.clear(screen.getByLabelText("修改数量"));
    await user.type(screen.getByLabelText("修改数量"), "120");
    await user.clear(screen.getByLabelText("修改成本"));
    await user.type(screen.getByLabelText("修改成本"), "2.15");
    await user.clear(screen.getByLabelText("修改市价"));
    await user.type(screen.getByLabelText("修改市价"), "2.8");
    await user.click(screen.getByRole("button", { name: "保存修改" }));

    expect(api.updatePosition).toHaveBeenCalledWith(7, {
      quantity: 120,
      avg_cost: 2.15,
      market_price: 2.8,
    });
  });

  it("shows product name in current positions without cost or market price columns", async () => {
    vi.mocked(api.positions).mockResolvedValue([
      {
        id: 7,
        account_id: 1,
        instrument_id: 2,
        account: {
          id: 1,
          account_code: "core",
          account_name: "核心账户",
          account_type: "core",
          status: "active",
        },
        instrument: {
          id: 2,
          symbol: "510300",
          name: "沪深300ETF",
          instrument_type: "etf",
          is_dca_eligible: false,
          status: "active",
        },
        quantity: 100,
        avg_cost: 2.1,
        market_price: 2.6,
        market_value: 260,
        unrealized_pnl: 50,
        unrealized_pnl_pct: 0.2381,
        weight_in_account: 0.2,
        position_status: "open",
      },
    ]);

    render(<PositionsPage />);

    expect(await screen.findByText("沪深300ETF")).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "数量" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "成本" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "市价" })).not.toBeInTheDocument();
  });

  it("temporarily hides fund search on the instruments page", () => {
    render(<InstrumentsPage />);

    expect(screen.queryByText("基金检索")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("关键词")).not.toBeInTheDocument();
  });

  it("marks current position profit and loss as emphasized signed text", async () => {
    vi.mocked(api.positions).mockResolvedValue([
      {
        id: 7,
        account_id: 1,
        instrument_id: 2,
        account: {
          id: 1,
          account_code: "core",
          account_name: "核心账户",
          account_type: "core",
          status: "active",
        },
        instrument: {
          id: 2,
          symbol: "510300",
          name: "沪深300ETF",
          instrument_type: "etf",
          is_dca_eligible: false,
          status: "active",
        },
        quantity: 100,
        avg_cost: 2.1,
        market_price: 2.6,
        market_value: 260,
        unrealized_pnl: 50,
        unrealized_pnl_pct: 0.2381,
        weight_in_account: 0.2,
        position_status: "open",
      },
    ]);

    render(<PositionsPage />);

    expect(await screen.findByText("+50.00")).toHaveClass("pnl-cell", "positive");
  });

  it("marks current position losses as negative text", async () => {
    vi.mocked(api.positions).mockResolvedValue([
      {
        id: 8,
        account_id: 1,
        instrument_id: 2,
        account: {
          id: 1,
          account_code: "core",
          account_name: "核心账户",
          account_type: "core",
          status: "active",
        },
        instrument: {
          id: 2,
          symbol: "510300",
          name: "沪深300ETF",
          instrument_type: "etf",
          is_dca_eligible: false,
          status: "active",
        },
        quantity: 100,
        avg_cost: 2.1,
        market_price: 1.9,
        market_value: 190,
        unrealized_pnl: -20,
        unrealized_pnl_pct: -0.0952,
        weight_in_account: 0.2,
        position_status: "open",
      },
    ]);

    render(<PositionsPage />);

    expect(await screen.findByText("-20.00")).toHaveClass("pnl-cell", "negative");
  });
});
