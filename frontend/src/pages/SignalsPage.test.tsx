import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SignalsPage } from "./SignalsPage";

const mockApi = vi.hoisted(() => ({
  strategySignals: vi.fn(),
}));

vi.mock("../api/endpoints", () => ({
  api: mockApi,
}));

describe("SignalsPage", () => {
  beforeEach(() => {
    mockApi.strategySignals.mockResolvedValue([
      {
        instrument_id: 31,
        symbol: "012734",
        name: "易方达人工智能ETF联接C",
        strategy: "CS人工智能",
        signal: "买入",
        signal_type: "buy",
        signal_date: "2026-05-11",
        execution_date: "2026-05-12",
        execution_timing: "T+1 15:00前",
        execution_price_note: "基金按执行日净值成交，信号生成时执行日净值未知。",
        risk_filter: {
          enabled: true,
          source: "fund_nav",
          suggestion: "执行日若明显转弱，可降低仓位或取消买入。",
        },
        latest_price: 1.2345,
        data_source: "基金净值",
        explanation: "价格突破10日高点",
      },
    ]);
  });

  it("shows signal date execution date and fund execution risk note", async () => {
    const user = userEvent.setup();
    render(<SignalsPage />);

    expect(await screen.findByText("2026-05-11")).toBeInTheDocument();
    expect(screen.getByText("2026-05-12 T+1 15:00前")).toBeInTheDocument();

    await user.click(screen.getByRole("row", { name: /012734/ }));

    expect(screen.getByText("成交说明")).toBeInTheDocument();
    expect(screen.getByText(/执行日净值/)).toBeInTheDocument();
    expect(screen.getByText("风控提示")).toBeInTheDocument();
    expect(screen.getByText(/降低仓位/)).toBeInTheDocument();
  });
});
