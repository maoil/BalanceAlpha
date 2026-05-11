export type Account = {
  id: number;
  account_code: string;
  account_name: string;
  account_type: string;
  description?: string | null;
  status: string;
};

export type AccountSummary = Account & {
  summary: {
    market_value: number;
    cost: number;
    unrealized_pnl: number;
    unrealized_pnl_pct: number;
    position_count: number;
  };
};

export type Instrument = {
  id: number;
  symbol: string;
  name: string;
  instrument_type: string;
  market?: string | null;
  trade_mode?: string | null;
  default_account_type?: string | null;
  default_strategy_template?: string | null;
  is_dca_eligible: boolean;
  dca_confirm_cycle?: number | null;
  status: string;
  notes?: string | null;
  backtest_config_key?: string | null;
  tracking_index?: string | null;
};

export type BacktestConfig = {
  key: string;
  name: string;
  strategy: string;
};

export type Position = {
  id: number;
  account_id: number;
  instrument_id: number;
  account?: Account | null;
  instrument?: Instrument | null;
  quantity: number;
  avg_cost: number;
  market_price: number;
  price_date?: string | null;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  today_pnl?: number | null;
  weight_in_account?: number | null;
  position_status: string;
  updated_at?: string | null;
};

export type TradeSourceOrder = {
  id: number;
  order_date?: string | null;
  expected_confirm_date?: string | null;
  actual_confirm_date?: string | null;
  confirm_nav?: number | null;
  confirm_quantity?: number | null;
  quote_date_used?: string | null;
  status?: string | null;
  linked_trade_id?: number | null;
};

export type Trade = {
  id: number;
  account_id: number;
  instrument_id: number;
  account?: Account | null;
  instrument?: Instrument | null;
  trade_date: string;
  trade_type: string;
  side?: string | null;
  quantity?: number | null;
  price?: number | null;
  amount?: number | null;
  fee?: number | null;
  reason_code?: string | null;
  notes?: string | null;
  source_type?: string | null;
  source_id?: number | null;
  source_order?: TradeSourceOrder | null;
};

export type ManualFundOrder = {
  id: number;
  account_id: number;
  instrument_id: number;
  account?: Account | null;
  instrument?: Instrument | null;
  order_date: string;
  expected_confirm_date?: string | null;
  actual_confirm_date?: string | null;
  trade_type: string;
  side: string;
  quantity?: number | null;
  amount?: number | null;
  fee?: number | null;
  confirm_nav?: number | null;
  confirm_quantity?: number | null;
  quote_date_used?: string | null;
  status: string;
  reason_code?: string | null;
  notes?: string | null;
  linked_trade_id?: number | null;
};

export type Signal = {
  id: number;
  batch_id?: string | null;
  batch_version: number;
  signal_date: string;
  account_id: number;
  instrument_id: number;
  account?: Account | null;
  instrument?: Instrument | null;
  signal_type: string;
  priority: number;
  reason_code?: string | null;
  explanation?: string | null;
  score?: number | null;
  risk_flag?: string | null;
  status: string;
};

export type StrategyTemplate = {
  id: number;
  template_code: string;
  template_name: string;
  account_type: string;
  description?: string | null;
  config: Record<string, unknown>;
  version: string;
  status: string;
};

export type SignalAiAnalysis = {
  id: number;
  signal_id: number;
  analysis_type?: string | null;
  provider?: string | null;
  model_name?: string | null;
  prompt_version?: string | null;
  summary?: string | null;
  confidence?: number | null;
  status: string;
  error_message?: string | null;
  output: Record<string, unknown>;
};

export type BacktestRun = {
  id: number;
  run_name: string;
  template_id?: number | null;
  template?: StrategyTemplate | null;
  start_date: string;
  end_date: string;
  params: Record<string, unknown>;
  result: Record<string, unknown>;
  summary: Record<string, unknown>;
  status: string;
  created_at?: string | null;
};

export type SystemLog = {
  id: number;
  log_type: string;
  level: string;
  module?: string | null;
  message: string;
  context: Record<string, unknown>;
  created_at?: string | null;
};

export type DashboardSnapshot = {
  totals: {
    market_value: number;
    cost: number;
    unrealized_pnl: number;
    unrealized_pnl_pct: number;
    position_count: number;
  };
  accounts: AccountSummary[];
  recent_trades: Trade[];
  pending_signals: Signal[];
  market_sentiment: Record<string, unknown>;
};

export type AssetTrendPoint = {
  date: string;
  total_assets: number;
  total_cost?: number;
  unrealized_pnl?: number;
  daily_pnl?: number;
  net_value: number;
  daily_return: number;
  cumulative_return: number;
};

export type AssetTrend = {
  series: AssetTrendPoint[];
  summary: Record<string, unknown>;
};

export type PerformanceSummary = {
  total_assets?: number;
  total_cost?: number;
  today_pnl?: number;
  change_vs_yesterday?: number;
  change_pct_vs_yesterday?: number;
  cumulative_return?: number;
  annualized_return?: number;
  as_of_date?: string | null;
};

export type StrategyPerformance = {
  strategy_name: string;
  return_7d?: number;
  win_rate?: number;
  max_drawdown?: number;
  status: string;
};

export type VixHistory = {
  series: Array<{ date: string; value: number }>;
  range?: string;
  interval?: string;
  source?: string;
};
