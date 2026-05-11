import { apiRequest, buildQuery, jsonBody, type QueryParams } from "./client";
import type {
  Account,
  AssetTrend,
  BacktestConfig,
  BacktestRun,
  DashboardSnapshot,
  Instrument,
  ManualFundOrder,
  PerformanceSummary,
  Position,
  Signal,
  SignalAiAnalysis,
  StrategyPerformance,
  StrategyTemplate,
  SystemLog,
  Trade,
  VixHistory,
} from "../types";

export const api = {
  health: () =>
    apiRequest<{ service: string; status: string; version: string }>("/health"),

  accounts: () => apiRequest<Account[]>("/accounts"),

  dashboard: () => apiRequest<DashboardSnapshot>("/dashboard"),
  assetTrend: (days = 30) =>
    apiRequest<AssetTrend>(`/dashboard/asset-trend${buildQuery({ days })}`),
  performanceSummary: () =>
    apiRequest<PerformanceSummary>("/dashboard/performance-summary"),

  backtestConfigs: () => apiRequest<BacktestConfig[]>("/backtest-configs"),

  instruments: (params: QueryParams = {}) =>
    apiRequest<Instrument[]>(`/instruments${buildQuery(params)}`),
  createInstrument: (payload: Record<string, unknown>) =>
    apiRequest<Instrument>("/instruments", {
      method: "POST",
      body: jsonBody(payload),
    }),
  updateInstrument: (id: number, payload: Record<string, unknown>) =>
    apiRequest<Instrument>(`/instruments/${id}`, {
      method: "PATCH",
      body: jsonBody(payload),
    }),
  updateInstrumentStatus: (id: number, status: string) =>
    apiRequest<Instrument>(`/instruments/${id}/status`, {
      method: "PATCH",
      body: jsonBody({ status }),
    }),
  searchFund: (keyword: string) =>
    apiRequest<Array<Record<string, unknown>>>(
      `/instruments/search-fund${buildQuery({ keyword })}`
    ),
  fundInfo: (fundCode: string) =>
    apiRequest<Record<string, unknown>>(`/instruments/fund-info/${fundCode}`),
  fetchInstrumentPrice: (id: number) =>
    apiRequest<Record<string, unknown>>(`/instruments/${id}/fetch-price`, {
      method: "POST",
    }),
  fetchInstrumentHistory: (id: number, days: number) =>
    apiRequest<Record<string, unknown>>(`/instruments/${id}/fetch-history`, {
      method: "POST",
      body: jsonBody({ days }),
    }),
  fetchAllPrices: () =>
    apiRequest<Record<string, unknown>>("/instruments/fetch-all-prices", {
      method: "POST",
    }),

  positions: (params: QueryParams = {}) =>
    apiRequest<Position[]>(`/positions${buildQuery(params)}`),
  createPosition: (payload: Record<string, unknown>) =>
    apiRequest<Position>("/positions", {
      method: "POST",
      body: jsonBody(payload),
    }),
  updatePosition: (id: number, payload: Record<string, unknown>) =>
    apiRequest<Position>(`/positions/${id}`, {
      method: "PATCH",
      body: jsonBody(payload),
    }),
  refreshPositions: () =>
    apiRequest<{ summary: Record<string, unknown>; positions: Position[] }>(
      "/positions/refresh",
      { method: "POST" }
    ),
  refreshPositionPrices: () =>
    apiRequest<{ updated: number; positions: Position[] }>(
      "/positions/refresh-prices",
      { method: "POST" }
    ),

  trades: (params: QueryParams = {}) =>
    apiRequest<Trade[]>(`/trades${buildQuery(params)}`),
  createTrade: (payload: Record<string, unknown>) =>
    apiRequest<Trade | ManualFundOrder>("/trades", {
      method: "POST",
      body: jsonBody(payload),
    }),

  manualFundOrders: (params: QueryParams = {}) =>
    apiRequest<ManualFundOrder[]>(`/manual-fund-orders${buildQuery(params)}`),
  confirmManualFundOrder: (id: number) =>
    apiRequest<{ order: ManualFundOrder; trade: Trade }>(
      `/manual-fund-orders/${id}/confirm`,
      { method: "POST" }
    ),

  signals: (params: QueryParams = {}) =>
    apiRequest<Signal[]>(`/signals${buildQuery(params)}`),
  generateSignals: (signalDate?: string) =>
    apiRequest<Signal[]>("/signals/generate", {
      method: "POST",
      body: jsonBody(signalDate ? { signal_date: signalDate } : {}),
    }),
  strategySignals: (instrumentId?: number) =>
    apiRequest<Array<Record<string, unknown>>>(
      `/strategy-signals${buildQuery(instrumentId ? { instrument_id: instrumentId } : {})}`
    ),
  signalHistory: (params: QueryParams = {}) =>
    apiRequest<Signal[]>(`/signals/history${buildQuery(params)}`),
  signalAiAnalysis: (id: number) =>
    apiRequest<SignalAiAnalysis | null>(`/signals/${id}/ai-analysis`),
  createSignalAiAnalysis: (id: number) =>
    apiRequest<SignalAiAnalysis>(`/signals/${id}/ai-analysis`, {
      method: "POST",
    }),
  createBatchAiAnalysis: (accountId?: number) =>
    apiRequest<Record<string, unknown>>("/signals/ai-analysis/batch", {
      method: "POST",
      body: jsonBody(accountId ? { account_id: accountId } : {}),
    }),
  rebalanceGuidance: (id: number) =>
    apiRequest<Record<string, unknown>>(`/signals/${id}/rebalance-guidance`),

  strategyTemplates: () =>
    apiRequest<StrategyTemplate[]>("/settings/strategy-templates"),
  updateStrategyTemplate: (id: number, payload: Record<string, unknown>) =>
    apiRequest<StrategyTemplate>(`/settings/strategy-templates/${id}`, {
      method: "PATCH",
      body: jsonBody(payload),
    }),
  strategyPerformance: (days = 7) =>
    apiRequest<StrategyPerformance[]>(
      `/strategies/performance${buildQuery({ days })}`
    ),

  backtests: (limit = 100) =>
    apiRequest<BacktestRun[]>(`/backtests${buildQuery({ limit })}`),
  createBacktest: (payload: Record<string, unknown>) =>
    apiRequest<BacktestRun>("/backtests", {
      method: "POST",
      body: jsonBody(payload),
    }),

  vixHistory: (days = 30, interval = "daily") =>
    apiRequest<VixHistory>(
      `/market/vix/history${buildQuery({ days, interval })}`
    ),
  logs: (params: QueryParams = {}) =>
    apiRequest<SystemLog[]>(`/logs${buildQuery(params)}`),
};
