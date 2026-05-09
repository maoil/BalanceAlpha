import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ManualFundOrdersPage } from "./ManualFundOrdersPage";

const mockApi = vi.hoisted(() => ({
  manualFundOrders: vi.fn(),
  confirmManualFundOrder: vi.fn(),
}));

vi.mock("../api/endpoints", () => ({
  api: mockApi,
}));

describe("ManualFundOrdersPage", () => {
  beforeEach(() => {
    mockApi.confirmManualFundOrder.mockResolvedValue({});
  });

  it("hides orders that have already been linked into holdings", async () => {
    mockApi.manualFundOrders.mockResolvedValue([
      {
        id: 1,
        account_id: 1,
        instrument_id: 1,
        account: { account_name: "核心账户" },
        instrument: { symbol: "161725", name: "白酒基金" },
        order_date: "2026-05-01",
        expected_confirm_date: "2026-05-02",
        trade_type: "subscribe",
        side: "buy",
        amount: 1000,
        status: "pending",
        linked_trade_id: null,
      },
      {
        id: 2,
        account_id: 1,
        instrument_id: 2,
        account: { account_name: "核心账户" },
        instrument: { symbol: "001938", name: "已确认基金" },
        order_date: "2026-04-20",
        expected_confirm_date: "2026-04-21",
        trade_type: "subscribe",
        side: "buy",
        amount: 800,
        status: "confirmed",
        linked_trade_id: 88,
      },
    ]);

    render(<ManualFundOrdersPage />);

    expect(await screen.findByText("161725")).toBeInTheDocument();
    expect(screen.queryByText("001938")).not.toBeInTheDocument();
    expect(screen.getByText("1 条")).toBeInTheDocument();
  });
});
