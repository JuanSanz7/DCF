import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { BookOpen, Check, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { DistPreview } from '../charts/charts'
import { api, type Dist, type ParamInput, type ParamSpec } from '../lib/api'
import { distLabel, fmtUnit, isPct } from '../lib/format'
import { SCALED_FIELDS, useMeta } from '../lib/meta'
import { Modal, NumberField, Segmented } from './ui'

const FIELD_LABEL: Record<string, string> = {
  mean: 'Mean', sd: 'Std. deviation', low: 'Minimum', high: 'Maximum', mode: 'Most likely', bound: 'Bound',
  lam: 'Peakedness (λ)', df: 'Degrees of freedom', side: 'Skew', values: 'Values', probs: 'Probabilities', smooth: 'Interpolate',
}

function defaults(kind: string, base: number, spec: ParamSpec): Dist {
  const s = Math.max(Math.abs(base) * 0.15, isPct(spec.unit) ? 0.01 : Math.abs(base) * 0.05 || 1)
  switch (kind) {
    case 'normal': return { kind, mean: base, sd: s }
    case 'truncnormal': return { kind, mean: base, sd: s, low: base - 3 * s, high: base + 3 * s }
    case 'lognormal': return { kind, mean: base, sd: s, bound: base - 2 * s, side: 'lower' }
    case 'triangular': return { kind, low: base - 2 * s, mode: base, high: base + 2 * s }
    case 'pert': return { kind, low: base - 2 * s, mode: base, high: base + 2 * s, lam: 4 }
    case 'uniform': return { kind, low: base - 2 * s, high: base + 2 * s }
    case 'student_t': return { kind, mean: base, sd: s, df: 5 }
    case 'discrete': return { kind, values: [base - s, base, base + s], probs: [0.25, 0.5, 0.25] }
    case 'empirical': return { kind, values: [base - s, base, base + s], smooth: true }
    default: return { kind: 'fixed' }
  }
}

export function DistEditor({ open, onOpenChange, spec, param, onApply, range }: {
  open: boolean; onOpenChange: (o: boolean) => void; spec: ParamSpec; param: ParamInput
  onApply: (d: Dist) => void; range?: [number, number] | null
}) {
  const { meta } = useMeta()
  const base = param.value ?? spec.default ?? 0
  const [d, setD] = useState<Dist>(param.dist ?? { kind: 'fixed' })
  useEffect(() => { if (open) setD(param.dist ?? { kind: 'fixed' }) }, [open, param.dist])
  const f = isPct(spec.unit) ? 100 : 1
  const unitSuffix = isPct(spec.unit) ? '%' : spec.unit === 'multiple' ? 'x' : spec.unit === 'money_m' ? 'm' : ''

  const [debounced, setDebounced] = useState(d)
  useEffect(() => { const t = setTimeout(() => setDebounced(d), 250); return () => clearTimeout(t) }, [d])
  const preview = useQuery({
    queryKey: ['preview', debounced], enabled: open && debounced.kind !== 'fixed',
    queryFn: () => api.preview(debounced), retry: false,
  })
  const sugg = useQuery({
    queryKey: ['suggest', spec.key, base, range?.[0], range?.[1]], enabled: open,
    queryFn: () => api.suggest({ key: spec.key, base, low: range?.[0], high: range?.[1] }),
  })
  const catalog = meta?.distributions ?? []
  const fields = catalog.find(c => c.kind === d.kind)?.fields ?? []

  const set = (k: string, v: unknown) => setD(prev => ({ ...prev, [k]: v }))
  const anchored = useMemo(() => {
    const m = preview.data?.mean
    if (m == null) return true
    return Math.abs(m - base) <= Math.max(0.1 * Math.abs(base), isPct(spec.unit) ? 0.002 : 1e-9)
  }, [preview.data, base, spec.unit])

  return (
    <Modal open={open} onOpenChange={onOpenChange} wide title={`Uncertainty: ${spec.label}`}
      description={`Base value ${fmtUnit(spec.unit, base)}. Choose how this input may vary across simulated futures.`}>
      <div className="grid gap-6 md:grid-cols-[230px_1fr]">
        <div>
          <p className="label mb-2">Shape</p>
          <ul className="space-y-0.5">
            {catalog.map(c => (
              <li key={c.kind}>
                <button onClick={() => setD(c.kind === d.kind ? d : defaults(c.kind, base, spec))}
                  className={clsx('w-full rounded-md px-2.5 py-1.5 text-left text-[13px]', c.kind === d.kind ? 'bg-ink text-white' : 'text-ink-2 hover:bg-paper')}>
                  {c.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="min-w-0 space-y-4">
          <p className="text-[13px] leading-relaxed text-ink-2">{catalog.find(c => c.kind === d.kind)?.when}</p>
          {d.kind !== 'fixed' && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
              {fields.map(k => (
                <label key={k} className={clsx('block', (k === 'values' || k === 'probs') && 'col-span-2 sm:col-span-4')}>
                  <span className="label">{FIELD_LABEL[k] ?? k}</span>
                  <div className="mt-1">
                    {k === 'side' ? (
                      <Segmented value={(d.side as string) ?? 'lower'} onChange={v => set('side', v)}
                        options={[{ value: 'lower', label: 'Floor', hint: 'Bound is a minimum: long right tail (upside surprises)' }, { value: 'upper', label: 'Cap', hint: 'Bound is a maximum: long left tail (downside surprises)' }]} size="xs" />
                    ) : k === 'smooth' ? (
                      <Segmented value={d.smooth ? 'y' : 'n'} onChange={v => set('smooth', v === 'y')}
                        options={[{ value: 'y', label: 'Smooth' }, { value: 'n', label: 'Exact' }]} size="xs" />
                    ) : k === 'values' || k === 'probs' ? (
                      <input className="field" defaultValue={((d[k] as number[]) ?? []).map(x => +(x * (k === 'values' ? f : 1)).toPrecision(8)).join(', ')}
                        placeholder={k === 'values' ? 'e.g. 12, 15.5, 18' : 'e.g. 0.25, 0.5, 0.25'}
                        onBlur={e => set(k, e.target.value.split(/[;\s]+|,\s+/).map(s => Number(s.replace(',', '.'))).filter(Number.isFinite).map(x => k === 'values' ? x / f : x))} />
                    ) : (
                      <NumberField value={d[k] == null ? null : (d[k] as number) * (SCALED_FIELDS.has(k) ? f : 1)}
                        suffix={SCALED_FIELDS.has(k) ? unitSuffix : undefined}
                        onCommit={v => set(k, v == null ? null : SCALED_FIELDS.has(k) ? v / f : v)} />
                    )}
                  </div>
                </label>
              ))}
              {('mean' in d || 'mode' in d) && (
                <div className="col-span-2 flex items-end sm:col-span-4">
                  <button className="btn-ghost" onClick={() => setD(prev => ('mode' in prev ? { ...prev, mode: base } : { ...prev, mean: base }))}>
                    Centre on the base value ({fmtUnit(spec.unit, base)})
                  </button>
                </div>
              )}
            </div>
          )}
          {d.kind !== 'fixed' && (
            <div className="rounded-md border border-rule p-3">
              {preview.error ? <p className="text-[12.5px] text-bad">{(preview.error as Error).message}</p> : preview.data?.density ? (
                <>
                  <DistPreview density={preview.data.density} unit={spec.unit} base={base} />
                  <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-ink-2">
                    <span>Mean <b className="text-ink">{fmtUnit(spec.unit, preview.data.mean)}</b></span>
                    <span>Std. dev. <b className="text-ink">{fmtUnit(spec.unit, preview.data.sd)}</b></span>
                    <span>P5–P95 <b className="text-ink">{fmtUnit(spec.unit, preview.data.p5)} – {fmtUnit(spec.unit, preview.data.p95)}</b></span>
                  </div>
                  {!anchored && <p className="mt-2 text-[12px] text-warn">The mean is away from the base value. Damodaran centres the distribution on the base-case expectation; otherwise the base case and the simulation describe different companies.</p>}
                </>
              ) : <div className="h-[120px]" />}
            </div>
          )}

          <div>
            <div className="mb-2 flex items-center gap-1.5"><Sparkles size={14} className="text-value" /><p className="section-title">Suggested for this input</p></div>
            {range && <p className="hint mb-2">Using the range from your notes: {fmtUnit(spec.unit, range[0])} to {fmtUnit(spec.unit, range[1])}.</p>}
            <ul className="space-y-2">
              {(sugg.data?.suggestions ?? []).map((s, i) => (
                <li key={i} className={clsx('rounded-md border p-3', s.recommended ? 'border-value/40 bg-value-soft/40' : 'border-rule')}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[13px] font-semibold">{s.title}{s.recommended && <span className="chip ml-2 bg-value text-white">Recommended</span>}</p>
                      <p className="mt-0.5 text-[12.5px] leading-relaxed text-ink-2">{s.rationale}</p>
                      <p className="mt-1 text-[12px] text-ink-3">{distLabel(s.dist, spec)}</p>
                    </div>
                    <button className="btn shrink-0" onClick={() => setD(s.dist)}>Use</button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <details className="rounded-md border border-rule px-3 py-2 text-[12.5px] text-ink-2">
            <summary className="flex cursor-pointer items-center gap-1.5 font-medium text-ink"><BookOpen size={14} /> How to choose (Damodaran's workflow)</summary>
            <ul className="mt-2 list-disc space-y-1 pl-5">{meta?.principles.map((p, i) => <li key={i}>{p}</li>)}</ul>
            <p className="mt-2">Sources: {meta?.sources.map((s, i) => <a key={i} href={s.url} target="_blank" rel="noreferrer" className="mr-3 underline decoration-dotted underline-offset-2 hover:text-value">{s.title}</a>)}</p>
          </details>
        </div>
      </div>
      <div className="mt-5 flex justify-end gap-2 border-t border-rule pt-4">
        <button className="btn" onClick={() => onOpenChange(false)}>Cancel</button>
        <button className="btn-primary" disabled={!!preview.error && d.kind !== 'fixed'} onClick={() => { onApply(d); onOpenChange(false) }}>
          <Check size={14} /> Apply
        </button>
      </div>
    </Modal>
  )
}
