// Typed client for the FastAPI backend.

export type Unit = 'percent' | 'money_m' | 'price' | 'shares_m' | 'ratio' | 'multiple' | 'years' | 'probability'

export interface ParamSpec {
  key: string; label: string; group: string; unit: Unit; description: string; help: string
  hard_min: number | null; hard_max: number | null; soft_min: number | null; soft_max: number | null
  default: number | null; category: string; stochastic_by_default: boolean; required: boolean
}
export interface DistCatalogItem { kind: string; label: string; fields: string[]; when: string }
export interface Meta {
  groups: Record<string, string>; parameters: ParamSpec[]; distributions: DistCatalogItem[]
  principles: string[]; sources: { title: string; url: string }[]; engine_version: string
}

export type Dist = { kind: string; [k: string]: unknown }
export interface ParamInput { value: number | null; dist?: Dist; source?: string | null; note?: string | null }
export interface Inputs {
  company: { ticker: string; name?: string; currency: string; yahoo_symbol?: string | null; as_of?: string | null }
  params: Record<string, ParamInput>
  model?: {
    stage1_years?: number; stage2_years?: number; stage2_mode?: 'flat' | 'fade'
    reinvestment_mode?: 'rate' | 'roic'; discount_mode?: 'direct' | 'build_up'
    wacc_fade?: boolean; mid_year?: boolean; tax_on_losses?: boolean
  }
  terminal?: { method?: 'rf_linked' | 'gordon' | 'exit_multiple'; wacc_source?: 'market' | 'direct' | 'explicit'; roic_mode?: 'equal_wacc' | 'spread' | 'absolute' }
  country_risk?: { region: string; weight: number; crp: number }[]
  simulation?: { n?: number; seed?: number | null; correlations?: { a: string; b: string; rho: number }[]; min_terminal_spread?: number }
}

export interface Issue { severity: 'error' | 'warning' | 'info'; code: string; message: string; param?: string | null }

export interface BaseCase {
  value_per_share: number | null; price: number | null; upside: number | null; ev: number | null
  pv_fcff: number | null; pv_tv: number | null; tv: number | null; tv_share: number | null; equity: number | null
  wacc: number | null; wacc_terminal: number | null; growth_terminal: number | null; roic_terminal: number | null
  reinvestment_terminal: number | null; nopat0: number | null
  table: { year: number[]; growth: number[]; nopat: number[]; reinvestment: number[]; roic: number[]; fcff: number[]; wacc: number[]; discount_factor: number[]; pv_fcff: number[] }
  bridge: Record<string, number | null>
}
export type Pcts = Record<string, number | null>
export interface Heatmap { x_key: string; y_key: string; x: number[]; y: number[]; x_edges: number[]; y_edges: number[]; median: (number | null)[][]; prob_above_price: (number | null)[][] | null; count: number[][] }
export interface Summary {
  n: number; n_valid: number; invalid_fraction: number; failed_fraction: number; seed: number
  clipped: Record<string, number>; correlation_adjusted: boolean; random_keys: string[]; base: BaseCase; price: number
  mean?: number; median?: number; sd?: number; sem?: number; skew?: number | null; percentiles?: Pcts; cvar5?: number
  prob_above_price?: number | null; upside_median?: number | null; upside_mean?: number | null
  histogram?: { edges: number[]; counts: number[]; below: number; above: number; total: number }
  ecdf?: { q: number[]; x: number[] }
  convergence?: { n: number[]; mean: number[]; median: number[]; lo: number[]; hi: number[] }
  tv_share?: Pcts; ev?: Pcts; wacc?: Pcts; wacc_terminal?: Pcts; growth_terminal?: Pcts
  fan?: { year: number[]; p5: number[]; p25: number[]; p50: number[]; p75: number[]; p95: number[]; base: number[]; mean?: number[]; sd?: number[] }
  sensitivity?: { key: string; label: string; rho: number | null; contribution: number }[]
  tornado?: { key: string; label: string; unit: Unit; input_low: number | null; input_high: number | null; value_low: number | null; value_high: number | null; base: number | null; swing: number }[]
  inputs?: Record<string, { label: string; unit: Unit; mean: number; sd?: number } & Pcts>
  sample?: Record<string, number[]>
  heatmaps?: Heatmap[]
  elapsed_ms?: number
  legacy?: unknown
}
export interface SimResponse { run_token: string; issues: Issue[]; summary: Summary; active: string[] }
export interface ValuationRow {
  id: string; ticker: string; name: string; created_at: string; label: string; notes: string; source: string
  engine_version: string; seed: number | null; n_paths: number; currency: string; price: number | null
  base_value: number | null; mean: number | null; median: number | null; sd: number | null
  p5: number | null; p10: number | null; p25: number | null; p75: number | null; p90: number | null; p95: number | null
  prob_above_price: number | null; tv_share: number | null; pinned: boolean; upside_median: number | null
}
export interface ValuationFull extends ValuationRow { inputs: Inputs | null; summary: Summary | null }
export interface CompanyRow {
  ticker: string; name: string; currency: string; yahoo_symbol: string | null; n_valuations: number
  latest: ValuationRow; history: { date: string; median: number | null; p10: number | null; p90: number | null; price: number | null }[]
}
export interface ImportField { value: number | string | null; raw: string | null; cell: string | null; note: string | null; range: [number, number] | null; ambiguous: boolean }
export interface ImportResponse {
  inputs: Inputs; tabs?: string[]; needs_tab?: boolean
  import: { source: string; locale: string | null; fields: Record<string, ImportField>; messages: { severity: string; message: string; key?: string | null }[] }
  check?: { sheet_value: number; model_value: number; match: boolean } | null
  history?: Record<string, unknown>
}
export interface Suggestion { dist: Dist; title: string; rationale: string; recommended: boolean }

export interface User { id: number; username: string }
export interface AuthStatus { user: User | null; signup_open: boolean; invite_required: boolean; persistent_storage: boolean; config_errors?: string[] }

export class ApiError extends Error {
  status: number; detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : detailText(detail))
    this.status = status; this.detail = detail
  }
}
function detailText(d: unknown): string {
  if (Array.isArray(d)) return d.map((x: { loc?: unknown[]; msg?: string }) => `${(x.loc ?? []).slice(-2).join('.')}: ${x.msg}`).join('; ')
  if (d && typeof d === 'object' && 'issues' in d) return ((d as { issues: Issue[] }).issues).filter(i => i.severity === 'error').map(i => i.message).join(' ')
  if (d && typeof d === 'object' && 'messages' in d) return ((d as { messages: { message: string }[] }).messages).map(m => m.message).join(' ')
  return 'Request failed'
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { credentials: 'same-origin', ...init, headers: init?.body instanceof FormData ? init?.headers : { 'Content-Type': 'application/json', ...init?.headers } })
  if (!r.ok) {
    let detail: unknown = r.statusText
    try { detail = (await r.json()).detail } catch { /* not json */ }
    if (r.status === 401 && !path.startsWith('/api/auth/')) window.dispatchEvent(new Event('dcf:unauthorized'))
    throw new ApiError(r.status, detail)
  }
  return r.json() as Promise<T>
}
const post = <T,>(p: string, body: unknown) => req<T>(p, { method: 'POST', body: JSON.stringify(body) })

export const api = {
  meta: () => req<Meta>('/api/meta'),
  authStatus: () => req<AuthStatus>('/api/auth/status'),
  login: (username: string, password: string) => post<{ user: User }>('/api/auth/login', { username, password }),
  signup: (username: string, password: string, invite?: string) => post<{ user: User }>('/api/auth/signup', { username, password, invite }),
  logout: () => post<{ ok: boolean }>('/api/auth/logout', {}),
  importLegacy: (file: File) => { const f = new FormData(); f.append('file', file); return req<{ imported: number; skipped: number }>('/api/import/legacy', { method: 'POST', body: f }) },
  template: (ticker: string, currency: string) => req<Inputs>(`/api/template?ticker=${encodeURIComponent(ticker)}&currency=${currency}`),
  validate: (inputs: Inputs) => post<{ issues: Issue[]; active: string[]; base: BaseCase | null; wacc: { mean: number; sd: number; p5: number; p50: number; p95: number } | null }>('/api/validate', inputs),
  simulate: (inputs: Inputs) => post<SimResponse>('/api/simulate', inputs),
  explore: (q: { x: string; y: string; run_token?: string; valuation_id?: string; bins?: number }) =>
    req<Heatmap>('/api/explore?' + new URLSearchParams(Object.entries(q).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]))),
  suggest: (b: { key: string; base: number | null; low?: number | null; high?: number | null; history?: number[] | null }) =>
    post<{ key: string; vary: boolean; suggestions: Suggestion[] }>('/api/suggest', b),
  preview: (d: Dist) => post<{ mean?: number; sd?: number; p5?: number; p10?: number; p50?: number; p90?: number; p95?: number; density?: { x: number[]; y: number[]; discrete: boolean } }>('/api/distribution/preview', d),
  save: (b: { run_token?: string; inputs?: Inputs; label?: string; notes?: string }) => post<ValuationFull>('/api/valuations', b),
  valuations: (ticker?: string) => req<ValuationRow[]>('/api/valuations' + (ticker ? `?ticker=${ticker}` : '')),
  valuation: (id: string) => req<ValuationFull>(`/api/valuations/${id}`),
  patchValuation: (id: string, b: { label?: string; notes?: string; pinned?: boolean }) => req<ValuationFull>(`/api/valuations/${id}`, { method: 'PATCH', body: JSON.stringify(b) }),
  deleteValuation: (id: string) => req<{ ok: boolean }>(`/api/valuations/${id}`, { method: 'DELETE' }),
  companies: () => req<CompanyRow[]>('/api/companies'),
  company: (t: string) => req<{ ticker: string; name: string; currency: string; yahoo_symbol: string | null; valuations: ValuationRow[] }>(`/api/companies/${t}`),
  prices: (symbol: string, start: string) => req<{ symbol: string; dates: string[]; close: number[] }>(`/api/prices/${encodeURIComponent(symbol)}?start=${start}`),
  settings: () => req<Record<string, unknown>>('/api/settings'),
  putSettings: (b: Record<string, unknown>) => req<Record<string, unknown>>('/api/settings', { method: 'PUT', body: JSON.stringify(b) }),
  sheetTabs: (url: string) => post<{ tabs: string[] }>('/api/import/sheet/tabs', { url }),
  importSheet: (url: string, tab?: string, with_notes = false) => post<ImportResponse>('/api/import/sheet', { url, tab, with_notes }),
  importExcel: (file: File, tab?: string) => { const f = new FormData(); f.append('file', file); if (tab) f.append('tab', tab); return req<ImportResponse>('/api/import/excel', { method: 'POST', body: f }) },
  importYahoo: (symbol: string) => req<ImportResponse>(`/api/import/yahoo/${encodeURIComponent(symbol)}`),
  searchTickers: (q: string) => req<{ symbol: string; name: string; exchange: string; type: string }[]>(`/api/tickers/search?q=${encodeURIComponent(q)}`),
}
