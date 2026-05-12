import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PositionsPage } from "./PositionsPage";

const mockApi = vi.hoisted(() => ({
  accounts: vi.fn(),
  positions: vi.fn(),
  positionTrends: vi.fn(),
  createPosition: vi.fn(),
  updatePosition: vi.fn(),
  refreshPositions: vi.fn(),
  refreshPositionPrices: vi.fn(),
}));

vi.mock("../api/endpoints", () => ({
  api: mockApi,
}));

describe("position trend list", () => {
  beforeEach(() => {
    mockApi.accounts.mockResolvedValue([]);
    mockApi.positionTrends.mockResolvedValue({ positions: [] });
    mockApi.createPosition.mockResolvedValue({});
    mockApi.updatePosition.mockResolvedValue({});
    mockApi.refreshPositions.mockResolvedValue({});
    mockApi.refreshPositionPrices.mockResolvedValue({});
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders a sparkline only when the API returns trend points", async () => {
    mockApi.positions.mockResolvedValue([
      {
        id: 1,
        account_id: 1,
        instrument_id: 10,
        account: null,
        instrument: {
          id: 10,
          symbol: "510500",
          name: "Trend Product",
          instrument_type: "etf",
          trade_mode: "exchange_traded",
          is_dca_eligible: false,
          status: "active",
        },
        quantity: 100,
        avg_cost: 2,
        market_price: 2.4,
        market_value: 240,
        unrealized_pnl: 40,
        unrealized_pnl_pct: 0.15,
        today_pnl: 3,
        position_status: "open",
      },
      {
        id: 2,
        account_id: 1,
        instrument_id: 20,
        account: null,
        instrument: {
          id: 20,
          symbol: "020840",
          name: "Unbound Fund",
          instrument_type: "fund",
          trade_mode: "eod_nav",
          is_dca_eligible: false,
          status: "active",
        },
        quantity: 100,
        avg_cost: 1,
        market_price: 1.1,
        market_value: 110,
        unrealized_pnl: 10,
        unrealized_pnl_pct: 0.1,
        today_pnl: null,
        position_status: "open",
      },
    ]);
    mockApi.positionTrends.mockResolvedValue({
      positions: [
        {
          position_id: 1,
          today_change_pct: 0.2,
          trend: {
            source_type: "instrument",
            interval: "intraday",
            symbol: "510500",
            points: [
              { time: "2026-05-12 09:31:00", value: 2.0 },
              { time: "2026-05-12 10:30:00", value: 2.2 },
              { time: "2026-05-12 14:55:00", value: 2.4 },
            ],
            change_pct: 0.2,
          },
        },
        {
          position_id: 2,
          today_change_pct: null,
          trend: null,
        },
      ],
    });

    render(<PositionsPage />);

    const sparkline = await screen.findByLabelText("Trend Product trend");

    expect(mockApi.positionTrends).toHaveBeenCalledWith({ account_id: undefined });
    expect(sparkline.querySelector("polyline")).toBeInTheDocument();
    expect(screen.getByText("+20.00%")).toBeInTheDocument();
    expect(screen.queryByLabelText("Unbound Fund trend")).not.toBeInTheDocument();
  });
});
