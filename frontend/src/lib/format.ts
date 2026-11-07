import type { Dist, ParamSpec, Unit } from './api'

export const isPct = (u: Unit) => u === 'percent' || u === 'probability'
export const toDisplay = (u: Unit, v: number | null | undefined) => (v == null ? null : isPct(u) ? v * 100 : v)
export const fromDisplay = (u: Unit, v: number | null) => (v == null ? null : isPct(u) ? v / 100 : v)

const nf = (d: number) => new Intl.NumberFormat('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })

export function fmtUnit(u: Unit, v: number | null | undefined, opts: { digits?: number } = {}): string {
  if (v == null || !Number.isFinite(v)) return '–'
  switch (u) {
    case 'percent': case 'probability': return nf(opts.digits ?? (Math.abs(v) < 0.1 ? 2 : 1)).format(v * 100) + '%'
    case 'money_m': return nf(opts.digits ?? 0).format(v) + 'm'
    case 'shares_m': return nf(opts.digits ?? 0).format(v) + 'm'
    case 'multiple': return nf(opts.digits ?? 1).format(v) + 'x'
    case 'price': return nf(opts.digits ?? 2).format(v)
    default: return nf(opts.digits ?? 2).format(v)
  }
}
export const fmtPct = (v: number | null | undefined, d = 1) => (v == null || !Number.isFinite(v) ? '–' : nf(d).format(v * 100) + '%')
export const fmtSignedPct = (v: number | null | undefined, d = 0) => (v == null || !Number.isFinite(v) ? '–' : (v > 0 ? '+' : '') + nf(d).format(v * 100) + '%')
export const fmtNum = (v: number | null | undefined, d = 2) => (v == null || !Number.isFinite(v) ? '–' : nf(d).format(v))
export const fmtMoney = (v: number | null | undefined, cur?: string, d = 2) => (v == null || !Number.isFinite(v) ? '–' : nf(d).format(v) + (cur ? ' ' + cur : ''))
export const fmtDate = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })

/** Short human label of a distribution in the parameter's own unit, e.g. "PERT 70–90–110%". */
export function distLabel(d: Dist | undefined, spec: ParamSpec): string {
  if (!d || d.kind === 'fixed') return 'Fixed'
  const f = (x: unknown) => fmtUnit(spec.unit, x as number)
  const n = (x: unknown) => { const s = f(x); return isPct(spec.unit) ? s.replace('%', '') : s }
  switch (d.kind) {
    case 'normal': return `Normal ±${f(d.sd)}`
    case 'truncnormal': return `Trunc. normal ±${f(d.sd)} [${n(d.low)}, ${f(d.high)}]`
    case 'lognormal': return `Lognormal ±${f(d.sd)}, ${d.side === 'upper' ? 'cap' : 'floor'} ${f(d.bound)}`
    case 'triangular': return `Triangular ${n(d.low)} – ${n(d.mode)} – ${f(d.high)}`
    case 'pert': return `PERT ${n(d.low)} – ${n(d.mode)} – ${f(d.high)}`
    case 'uniform': return `Uniform ${n(d.low)} – ${f(d.high)}`
    case 'student_t': return `Student-t ±${f(d.sd)}, df ${d.df}`
    case 'discrete': return `Discrete (${(d.values as number[]).length} outcomes)`
    case 'empirical': return `Empirical (${(d.values as number[]).length} obs.)`
    default: return d.kind
  }
}
