import * as Tabs from '@radix-ui/react-tabs'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { CircleHelp, Dice5, Download, Plus, Save, SlidersHorizontal, Trash2, Upload } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { CdfChart, ConvergenceChart, FanChart, HeatmapChart, ScatterExplorer, Tornado, ValueField } from '../charts/charts'
import { DistEditor } from '../components/DistEditor'
import { ImportDialog } from '../components/ImportDialog'
import { Empty, IssueList, NumberField, Segmented, Spinner, Tip } from '../components/ui'
import { api, type BaseCase, type Dist, type Heatmap, type Inputs, type Issue, type ParamInput, type ParamSpec, type Summary } from '../lib/api'
import { distLabel, fmtDate, fmtMoney, fmtNum, fmtPct, fmtSignedPct, fmtUnit, isPct, toDisplay } from '../lib/format'
import { useMeta } from '../lib/meta'

const DRAFT = 'dcf:draft'
type Model = NonNullable<Inputs['model']>
type Term = NonNullable<Inputs['terminal']>

export default function Workspace() {
  const { id } = useParams()
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { meta, specs } = useMeta()
  const [inputs, setInputs] = useState<Inputs | null>(null)
  const [ranges, setRanges] = useState<Record<string, [number, number]>>({})
  const [summary, setSummary] = useState<Summary | null>(null)
  const [runToken, setRunToken] = useState<string | null>(null)
  const [savedId, setSavedId] = useState<string | null>(id ?? null)
  const [savedAt, setSavedAt] = useState<string | null>(null)
  const [dirtySinceRun, setDirtySinceRun] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)
  const [label, setLabel] = useState('')
  const [notes, setNotes] = useState('')
  const [simErr, setSimErr] = useState<string | null>(null)
  const ledgerRef = useRef<HTMLDivElement>(null)

  // ---------------------------------------------------------------- load
  const saved = useQuery({ queryKey: ['valuation', id], queryFn: () => api.valuation(id!), enabled: !!id })
  useEffect(() => {
    if (id) {
      if (saved.data?.inputs && !('_legacy' in saved.data.inputs)) {
        setInputs(saved.data.inputs); setSummary(saved.data.summary); setSavedId(saved.data.id)
        setSavedAt(saved.data.created_at); setLabel(saved.data.label); setNotes(saved.data.notes); setDirtySinceRun(false)
      }
      return
    }
    const ticker = sp.get('ticker')
    const draft = localStorage.getItem(DRAFT)
    if (draft && !ticker) { try { const d = JSON.parse(draft); setInputs(d.inputs); setRanges(d.ranges ?? {}); return } catch { /* ignore */ } }
    api.template(ticker ?? 'NEW', sp.get('currency') ?? 'USD').then(t => { setInputs(t); if (!ticker) setImportOpen(true) })
  }, [id, saved.data, sp])

  useEffect(() => { if (!id && inputs) localStorage.setItem(DRAFT, JSON.stringify({ inputs, ranges })) }, [inputs, ranges, id])

  // ---------------------------------------------------------------- live validation
  const [debounced, setDebounced] = useState(inputs)
  useEffect(() => { const t = setTimeout(() => setDebounced(inputs), 300); return () => clearTimeout(t) }, [inputs])
  const val = useQuery({ queryKey: ['validate', debounced], queryFn: () => api.validate(debounced!), enabled: !!debounced, placeholderData: p => p, retry: false })
  const issues: Issue[] = val.data?.issues ?? []
  const active = val.data?.active ?? []
  const errors = issues.filter(i => i.severity === 'error')
  const base: BaseCase | null = val.data?.base ?? null

  const update = useCallback((fn: (d: Inputs) => Inputs) => { setInputs(prev => (prev ? fn(structuredClone(prev)) : prev)); setDirtySinceRun(true) }, [])
  const setParam = (key: string, patch: Partial<ParamInput>) => update(d => {
    const cur = d.params[key] ?? { value: null }
    const next = { ...cur, ...patch }
    // keep a distribution centred on the base when the base moves (shift its location)
    if ('value' in patch && cur.dist && cur.dist.kind !== 'fixed' && cur.value != null && patch.value != null) {
      const shift = patch.value - cur.value
      const dd = { ...cur.dist } as Record<string, unknown>
      for (const k of ['mean', 'low', 'high', 'mode', 'bound']) if (typeof dd[k] === 'number') dd[k] = (dd[k] as number) + shift
      if (Array.isArray(dd.values)) dd.values = (dd.values as number[]).map(v => v + shift)
      next.dist = dd as Dist
    }
    if ('value' in patch) next.source = 'manual'
    d.params[key] = next
    return d
  })
  const setModel = (patch: Partial<Model>) => update(d => ({ ...d, model: { ...d.model, ...patch } }))
  const setTerm = (patch: Partial<Term>) => update(d => ({ ...d, terminal: { ...d.terminal, ...patch } }))

  // ---------------------------------------------------------------- run / save
  const sim = useMutation({
    mutationFn: () => api.simulate(inputs!),
    onMutate: () => setSimErr(null),
    onSuccess: r => { setSummary(r.summary); setRunToken(r.run_token); setDirtySinceRun(false); setSavedId(null); setSavedAt(null) },
    onError: (e: Error) => setSimErr(e.message),
  })
  const save = useMutation({
    mutationFn: () => api.save({ run_token: runToken ?? undefined, inputs: inputs!, label, notes }),
    onSuccess: v => {
      setSavedId(v.id); setSavedAt(v.created_at); localStorage.removeItem(DRAFT)
      qc.invalidateQueries({ queryKey: ['companies'] }); qc.invalidateQueries({ queryKey: ['company'] })
      nav(`/v/${v.id}`, { replace: true })
    },
  })

  const onImport = (imp: Inputs, mode: 'replace' | 'merge', rg: Record<string, [number, number]>) => {
    setRanges(prev => (mode === 'replace' ? rg : { ...prev, ...rg }))
    if (mode === 'replace' || !inputs) {
      setInputs(prev => ({ ...imp, simulation: { ...(prev?.simulation ?? {}), ...(imp.simulation ?? {}) } }))
    } else {
      update(d => {
        for (const [k, p] of Object.entries(imp.params)) d.params[k] = { ...(d.params[k] ?? {}), value: p.value, source: p.source, note: p.note ?? d.params[k]?.note }
        d.company = { ...d.company, ...Object.fromEntries(Object.entries(imp.company).filter(([, v]) => v)) }
        return d
      })
    }
    setSummary(null); setRunToken(null); setSavedId(null); setDirtySinceRun(true)
    if (id) nav('/new', { replace: true })
  }

  if (!inputs || !meta) return <div className="p-10"><Spinner /></div>
  if (id && saved.data?.inputs && '_legacy' in saved.data.inputs) return <LegacyView v={saved.data} />

  const cur = inputs.company.currency
  const model = inputs.model ?? {}
  const term = inputs.terminal ?? {}
  const groups = Object.entries(meta.groups)
  const issuesByParam: Record<string, Issue[]> = {}
  issues.forEach(i => { if (i.param) (issuesByParam[i.param] ??= []).push(i) })
  const randomKeys = active.filter(k => inputs.params[k]?.dist && inputs.params[k]!.dist!.kind !== 'fixed')

  const goTo = (key: string) => {
    const el = document.getElementById(`param-${key}`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el?.querySelector('input')?.focus()
  }

  return (
    <div className="mx-auto max-w-[1600px] px-4 pb-16 lg:px-6">
      {/* ------------------------------------------------ header */}
      <div className="sticky top-12 z-20 -mx-4 mb-4 border-b border-rule bg-paper/95 px-4 py-3 backdrop-blur lg:-mx-6 lg:px-6">
        <div className="flex flex-wrap items-end gap-3">
          <label className="w-28"><span className="label">Ticker</span>
            <input className="field mt-1 font-semibold uppercase" value={inputs.company.ticker} onChange={e => update(d => ({ ...d, company: { ...d.company, ticker: e.target.value.toUpperCase() } }))} /></label>
          <label className="min-w-48 flex-1"><span className="label">Company</span>
            <input className="field mt-1" value={inputs.company.name ?? ''} placeholder="Company name" onChange={e => update(d => ({ ...d, company: { ...d.company, name: e.target.value } }))} /></label>
          <label className="w-20"><span className="label">Currency</span>
            <input className="field mt-1 uppercase" maxLength={3} value={inputs.company.currency} onChange={e => update(d => ({ ...d, company: { ...d.company, currency: e.target.value.toUpperCase() } }))} /></label>
          <label className="w-32"><span className="label">Yahoo symbol</span>
            <input className="field mt-1" value={inputs.company.yahoo_symbol ?? ''} placeholder="for prices" onChange={e => update(d => ({ ...d, company: { ...d.company, yahoo_symbol: e.target.value.toUpperCase() || null } }))} /></label>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button className="btn" onClick={() => setImportOpen(true)}><Upload size={14} /> Load data</button>
            <button className="btn" onClick={() => { localStorage.removeItem(DRAFT); nav('/new?ticker=NEW'); window.location.reload() }}><Plus size={14} /> Blank</button>
            <button className="btn-primary h-9 px-4" disabled={errors.length > 0 || sim.isPending} onClick={() => sim.mutate()}>
              {sim.isPending ? <Spinner /> : <Dice5 size={15} />} Run {(inputs.simulation?.n ?? 20000).toLocaleString('en-US')} paths
            </button>
          </div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(470px,560px)_1fr]">
        {/* ------------------------------------------------ ledger */}
        <div ref={ledgerRef} className="space-y-6">
          <ModelPanel model={model} term={term} setModel={setModel} setTerm={setTerm} />
          {groups.map(([g, title]) => {
            const keys = active.filter(k => specs[k]?.group === g)
            if (!keys.length) return null
            return (
              <section key={g}>
                <h2 className="section-title mb-1.5 border-b border-rule pb-1.5">{title}</h2>
                <div className="divide-y divide-rule/70">
                  {keys.map(k => (
                    <ParamRow key={k} spec={specs[k]} p={inputs.params[k] ?? { value: null }} currency={cur}
                      issues={issuesByParam[k] ?? []} range={ranges[k]}
                      onValue={v => setParam(k, { value: v })} onEditDist={() => setEditing(k)} />
                  ))}
                </div>
              </section>
            )
          })}
          <SimPanel inputs={inputs} update={update} randomKeys={randomKeys} specs={specs} />
        </div>

        {/* ------------------------------------------------ readout */}
        <div className="min-w-0 space-y-5">
          <BaseReadout base={base} currency={cur} pending={val.isFetching} />
          <IssueList issues={visibleIssues(issues)} onPick={goTo} />
          {simErr && <p className="rounded-md bg-bad-soft px-3 py-2 text-[13px] text-bad">{simErr}</p>}
          {summary?.histogram ? (
            <Results s={summary} specs={specs} currency={cur} runToken={runToken} savedId={savedId} stale={dirtySinceRun}
              savedAt={savedAt} label={label} notes={notes} setLabel={setLabel} setNotes={setNotes}
              onSave={() => save.mutate()} saving={save.isPending} saveError={save.error?.message ?? null} ticker={inputs.company.ticker} />
          ) : (
            <Empty title="Run the simulation to see the value field">
              The base case above updates as you type. Give the inputs you are unsure about a distribution (click the shape next to each value; the advisor suggests one), then run the simulation to see every plausible value against the market price.
            </Empty>
          )}
        </div>
      </div>

      {editing && specs[editing] && (
        <DistEditor open onOpenChange={o => !o && setEditing(null)} spec={specs[editing]} param={inputs.params[editing] ?? { value: null }}
          range={ranges[editing]} onApply={dist => setParam(editing, { dist })} />
      )}
      <ImportDialog open={importOpen} onOpenChange={setImportOpen} onApply={onImport} defaultSymbol={inputs.company.yahoo_symbol ?? undefined} />
    </div>
  )
}

function visibleIssues(issues: Issue[]): Issue[] {
  const shown = issues.filter(i => i.severity !== 'info' || i.code.startsWith('implied'))
  const missing = shown.filter(i => i.code === 'missing')
  if (missing.length <= 3) return shown
  return [{ severity: 'error', code: 'missing_many', message: `${missing.length} inputs still need a base value; they are marked in red. Load a template tab or type them in.` },
    ...shown.filter(i => i.code !== 'missing')]
}

// ======================================================================= ledger rows
function ParamRow({ spec, p, currency, issues, range, onValue, onEditDist }: {
  spec: ParamSpec; p: ParamInput; currency: string; issues: Issue[]; range?: [number, number]
  onValue: (v: number | null) => void; onEditDist: () => void
}) {
  const err = issues.some(i => i.severity === 'error')
  const warn = issues.some(i => i.severity === 'warning')
  const random = p.dist && p.dist.kind !== 'fixed'
  const suffix = isPct(spec.unit) ? '%' : spec.unit === 'money_m' || spec.unit === 'shares_m' ? 'm' : spec.unit === 'multiple' ? 'x' : spec.unit === 'price' ? currency : ''
  const value = p.value ?? null
  return (
    <div id={`param-${spec.key}`} className="grid grid-cols-[minmax(0,1fr)_118px] items-center gap-x-3 gap-y-1 py-1.5 sm:grid-cols-[minmax(0,1fr)_118px_minmax(0,1fr)]">
      <div className="min-w-0">
        <div className="flex items-center gap-1">
          <span className={clsx('truncate text-[13px]', err ? 'text-bad' : 'text-ink')}>{spec.label}</span>
          <Tip content={<><p className="font-medium text-ink">{spec.description}</p>{spec.help && <p className="mt-1">{spec.help}</p>}
            {p.source && <p className="mt-1 text-ink-3">Source: {p.source}</p>}{p.note && <p className="mt-1 text-ink-3">{p.note}</p>}</>}>
            <button className="text-ink-3 hover:text-ink" aria-label={`About ${spec.label}`}><CircleHelp size={13} /></button>
          </Tip>
          {warn && !err && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-warn" title="See the warning" />}
        </div>
        {p.source && p.source !== 'manual' && <p className="truncate text-[11px] text-ink-3">{p.source}</p>}
      </div>
      <NumberField value={toDisplay(spec.unit, value)} suffix={suffix} invalid={err} ariaLabel={spec.label}
        onCommit={v => onValue(v == null ? null : isPct(spec.unit) ? v / 100 : v)} placeholder={spec.default != null ? String(toDisplay(spec.unit, spec.default)) : ''} />
      <button onClick={onEditDist} title={random ? distLabel(p.dist, spec) : 'Click to give this input a distribution'}
        className={clsx('col-span-2 flex h-8 min-w-0 items-center gap-1.5 rounded-md border px-2 text-left text-[12px] sm:col-span-1',
          random ? 'border-value/40 bg-value-soft/50 text-ink hover:border-value' : 'border-dashed border-rule text-ink-3 hover:border-rule-strong hover:text-ink')}>
        <SlidersHorizontal size={12} className={random ? 'text-value' : ''} />
        <span className="truncate">{random ? distLabel(p.dist, spec) : range ? 'Fixed, range in notes' : 'Fixed'}</span>
      </button>
    </div>
  )
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 py-1.5">
      <span className="flex items-center gap-1 text-[13px]">{label}{hint && <Tip content={hint}><button className="text-ink-3 hover:text-ink" aria-label="Help"><CircleHelp size={13} /></button></Tip>}</span>
      {children}
    </div>
  )
}

function ModelPanel({ model, term, setModel, setTerm }: { model: Model; term: Term; setModel: (p: Partial<Model>) => void; setTerm: (p: Partial<Term>) => void }) {
  return (
    <section>
      <h2 className="section-title mb-1.5 border-b border-rule pb-1.5">Model structure</h2>
      <div className="divide-y divide-rule/70">
        <Row label="Forecast years" hint="Stage 1 is the high-growth period; stage 2 is the transition to stable growth. The terminal value starts after the last year.">
          <div className="flex items-center gap-2 text-[12px] text-ink-3">
            stage 1 <NumberField className="w-14" value={model.stage1_years ?? 5} onCommit={v => setModel({ stage1_years: Math.max(1, Math.round(v ?? 5)) })} />
            stage 2 <NumberField className="w-14" value={model.stage2_years ?? 5} onCommit={v => setModel({ stage2_years: Math.max(0, Math.round(v ?? 5)) })} />
          </div>
        </Row>
        <Row label="Stage 2" hint="Flat uses the stage-2 inputs. Fade moves growth (and reinvestment or ROIC) linearly from stage 1 to the terminal values, the Damodaran default, so there is no cliff in the terminal year.">
          <Segmented value={model.stage2_mode ?? 'flat'} onChange={v => setModel({ stage2_mode: v })} options={[{ value: 'flat', label: 'Own inputs' }, { value: 'fade', label: 'Fade to terminal' }]} />
        </Row>
        <Row label="Reinvestment" hint="Rate: you set reinvestment directly. ROIC-linked: reinvestment = growth / return on new capital, so every simulated path stays internally consistent (Damodaran's fundamental growth equation).">
          <Segmented value={model.reinvestment_mode ?? 'rate'} onChange={v => setModel({ reinvestment_mode: v })} options={[{ value: 'rate', label: 'Rate' }, { value: 'roic', label: 'ROIC-linked' }]} />
        </Row>
        <Row label="Discount rate" hint="Build-up computes WACC from Rf, beta, ERP and the debt spread, so a simulated change in Rf moves the WACC, the terminal growth and the terminal WACC together.">
          <Segmented value={model.discount_mode ?? 'direct'} onChange={v => setModel({ discount_mode: v })} options={[{ value: 'build_up', label: 'Build-up' }, { value: 'direct', label: 'Direct WACC' }]} />
        </Row>
        <Row label="Terminal value" hint="Rf-linked: stable growth = risk-free rate (Damodaran's cap). Gordon: your own stable growth. Exit multiple: EV/EBIT on the last year (a relative valuation in disguise).">
          <Segmented value={term.method ?? 'rf_linked'} onChange={v => setTerm({ method: v })} options={[{ value: 'rf_linked', label: 'g = Rf' }, { value: 'gordon', label: 'Gordon' }, { value: 'exit_multiple', label: 'Exit multiple' }]} />
        </Row>
        {term.method !== 'exit_multiple' && <>
          <Row label="Terminal WACC" hint="Mature firm: Rf + terminal beta × ERP (with optional terminal debt). Your template uses beta = 1 and no debt. Direct: your own number. Same as explicit: keep the stage-1 WACC.">
            <Segmented value={term.wacc_source ?? 'market'} onChange={v => setTerm({ wacc_source: v })} options={[{ value: 'market', label: 'Mature firm' }, { value: 'direct', label: 'Direct' }, { value: 'explicit', label: 'Same as explicit' }]} />
          </Row>
          <Row label="Terminal ROIC" hint="ROIC = WACC means growth creates no value in perpetuity (conservative default). A spread above WACC describes a moat that never fully erodes.">
            <Segmented value={term.roic_mode ?? 'equal_wacc'} onChange={v => setTerm({ roic_mode: v })} options={[{ value: 'equal_wacc', label: '= WACC' }, { value: 'spread', label: 'WACC + spread' }, { value: 'absolute', label: 'Absolute' }]} />
          </Row>
        </>}
        <Row label="Fade WACC to terminal" hint="Moves the discount rate linearly from the explicit WACC to the terminal WACC across stage 2.">
          <Segmented value={model.wacc_fade ? 'y' : 'n'} onChange={v => setModel({ wacc_fade: v === 'y' })} options={[{ value: 'n', label: 'Off' }, { value: 'y', label: 'On' }]} size="xs" />
        </Row>
        <Row label="Mid-year discounting" hint="Cash flows arrive through the year, not on 31 December; discounting at mid-year raises value slightly.">
          <Segmented value={model.mid_year ? 'y' : 'n'} onChange={v => setModel({ mid_year: v === 'y' })} options={[{ value: 'n', label: 'Off' }, { value: 'y', label: 'On' }]} size="xs" />
        </Row>
      </div>
    </section>
  )
}

function SimPanel({ inputs, update, randomKeys, specs }: { inputs: Inputs; update: (fn: (d: Inputs) => Inputs) => void; randomKeys: string[]; specs: Record<string, ParamSpec> }) {
  const sim = inputs.simulation ?? {}
  const corr = sim.correlations ?? []
  const crp = inputs.country_risk ?? []
  const setSim = (patch: Partial<NonNullable<Inputs['simulation']>>) => update(d => ({ ...d, simulation: { ...d.simulation, ...patch } }))
  return (
    <section>
      <h2 className="section-title mb-1.5 border-b border-rule pb-1.5">Simulation</h2>
      <div className="divide-y divide-rule/70">
        <Row label="Paths" hint="More paths give stable tails. 20,000 is plenty for percentiles; 100,000+ for smooth heat maps.">
          <NumberField className="w-28" value={sim.n ?? 20000} onCommit={v => setSim({ n: Math.min(2_000_000, Math.max(100, Math.round(v ?? 20000))) })} />
        </Row>
        <Row label="Random seed" hint="Leave empty for a fresh draw each run. Set a number to reproduce a run exactly (the seed is saved with every valuation).">
          <NumberField className="w-28" value={sim.seed ?? null} placeholder="random" onCommit={v => setSim({ seed: v == null ? null : Math.round(v) })} />
        </Row>
      </div>
      <div className="mt-3">
        <div className="flex items-center justify-between"><span className="flex items-center gap-1 text-[13px]">Correlations
          <Tip content="Inputs that move together in reality (growth and reinvestment, Rf and ERP). Applied with a Gaussian copula, so any mix of shapes works. Damodaran used 0.5 between Apple's revenue growth and margin."><button className="text-ink-3" aria-label="Help"><CircleHelp size={13} /></button></Tip></span>
          <button className="btn-ghost" disabled={randomKeys.length < 2} onClick={() => update(d => ({ ...d, simulation: { ...d.simulation, correlations: [...corr, { a: randomKeys[0], b: randomKeys[1], rho: 0.5 }] } }))}><Plus size={13} /> Add</button>
        </div>
        {randomKeys.length < 2 && <p className="hint">Give at least two inputs a distribution to correlate them.</p>}
        {corr.map((c, i) => (
          <div key={i} className="mt-1.5 grid grid-cols-[1fr_1fr_80px_28px] items-center gap-2">
            {(['a', 'b'] as const).map(side => (
              <select key={side} className="field" value={c[side]} onChange={e => update(d => { d.simulation!.correlations![i][side] = e.target.value; return d })}>
                {randomKeys.map(k => <option key={k} value={k}>{specs[k]?.label}</option>)}
              </select>
            ))}
            <NumberField value={c.rho} onCommit={v => update(d => { d.simulation!.correlations![i].rho = Math.max(-0.99, Math.min(0.99, v ?? 0)); return d })} />
            <button className="btn-ghost" aria-label="Remove" onClick={() => update(d => { d.simulation!.correlations!.splice(i, 1); return d })}><Trash2 size={13} /></button>
          </div>
        ))}
      </div>
      <div className="mt-4">
        <div className="flex items-center justify-between"><span className="flex items-center gap-1 text-[13px]">Country risk by revenue
          <Tip content="Adds a revenue-weighted country risk premium to the mature ERP: ERP = mature ERP + Σ weight × CRP (Damodaran's operations-weighted approach). Applies to the explicit and the terminal cost of equity."><button className="text-ink-3" aria-label="Help"><CircleHelp size={13} /></button></Tip></span>
          <button className="btn-ghost" onClick={() => update(d => ({ ...d, country_risk: [...crp, { region: 'Region', weight: 0.1, crp: 0.01 }] }))}><Plus size={13} /> Add</button>
        </div>
        {crp.map((c, i) => (
          <div key={i} className="mt-1.5 grid grid-cols-[1fr_90px_90px_28px] items-center gap-2">
            <input className="field" value={c.region} onChange={e => update(d => { d.country_risk![i].region = e.target.value; return d })} />
            <NumberField value={c.weight * 100} suffix="%" onCommit={v => update(d => { d.country_risk![i].weight = Math.max(0, Math.min(1, (v ?? 0) / 100)); return d })} />
            <NumberField value={c.crp * 100} suffix="%" onCommit={v => update(d => { d.country_risk![i].crp = Math.max(0, (v ?? 0) / 100); return d })} />
            <button className="btn-ghost" aria-label="Remove" onClick={() => update(d => { d.country_risk!.splice(i, 1); return d })}><Trash2 size={13} /></button>
          </div>
        ))}
        {crp.length > 0 && <p className="hint mt-1">Columns: region, revenue weight, country risk premium.</p>}
      </div>
    </section>
  )
}

// ======================================================================= readouts
function BaseReadout({ base, currency, pending }: { base: BaseCase | null; currency: string; pending: boolean }) {
  if (!base) return null
  const up = base.upside
  return (
    <div className={clsx('grid grid-cols-2 gap-x-6 gap-y-3 rounded-lg border border-rule bg-panel px-5 py-4 sm:grid-cols-4', pending && 'opacity-70')}>
      <div>
        <p className="label">Base case value</p>
        <p className="font-cond text-[26px] font-semibold leading-tight">{fmtNum(base.value_per_share)} <span className="text-[14px] font-normal text-ink-3">{currency}</span></p>
        <p className={clsx('text-[12.5px] font-medium', up != null && up >= 0 ? 'text-value' : 'text-market')}>{fmtSignedPct(up)} vs price {fmtNum(base.price)}</p>
      </div>
      <Kv k="WACC → terminal" v={`${fmtPct(base.wacc, 2)} → ${fmtPct(base.wacc_terminal, 2)}`} />
      <Kv k="Terminal growth · reinvestment" v={`${fmtPct(base.growth_terminal, 2)} · ${fmtPct(base.reinvestment_terminal, 0)}`} />
      <Kv k="Terminal value share of EV" v={fmtPct(base.tv_share, 0)} />
    </div>
  )
}
const Kv = ({ k, v }: { k: string; v: string }) => <div><p className="label">{k}</p><p className="mt-1 text-[15px] font-medium tabular-nums">{v}</p></div>

function Results({ s, specs, currency, runToken, savedId, savedAt, stale, label, notes, setLabel, setNotes, onSave, saving, saveError, ticker }: {
  s: Summary; specs: Record<string, ParamSpec>; currency: string; runToken: string | null; savedId: string | null; savedAt: string | null
  stale: boolean; label: string; notes: string; setLabel: (v: string) => void; setNotes: (v: string) => void
  onSave: () => void; saving: boolean; saveError: string | null; ticker: string
}) {
  const p = s.percentiles!
  const prob = s.prob_above_price ?? 0
  return (
    <div className="space-y-5">
      {stale && <p className="rounded-md bg-warn-soft px-3 py-2 text-[12.5px] text-warn">Inputs changed since this run. Run again to update the results.</p>}
      <div className="rounded-lg border border-rule bg-panel">
        <div className="flex flex-wrap items-end gap-x-8 gap-y-3 border-b border-rule px-5 pb-4 pt-4">
          <div>
            <p className="label">Chance the value exceeds the price</p>
            <p className={clsx('font-cond text-[44px] font-semibold leading-none tracking-tight', prob >= 0.5 ? 'text-value' : 'text-market')}>{fmtPct(prob, 0)}</p>
          </div>
          <Kv k={`Median value (${currency})`} v={`${fmtNum(s.median)}  (${fmtSignedPct(s.upside_median)})`} />
          <Kv k="P10 – P90" v={`${fmtNum(p.p10)} – ${fmtNum(p.p90)}`} />
          <Kv k="Mean · std. dev." v={`${fmtNum(s.mean)} · ${fmtNum(s.sd)}`} />
          <Kv k="Market price" v={fmtNum(s.price)} />
        </div>
        <div className="px-3 pt-2">
          <ValueField s={s} currency={currency} />
        </div>
        <p className="px-5 pb-4 text-[12.5px] text-ink-2">
          {s.n_valid.toLocaleString('en-US')} valid paths{s.invalid_fraction > 0 && <> ({fmtPct(s.invalid_fraction, 1)} dropped: terminal WACC too close to growth)</>}.
          {' '}Bars right of the magenta line are futures in which the stock is worth more than its price. Buying at the P20 ({fmtNum(p.p20)}) leaves a margin of safety in four out of five paths.
          {s.elapsed_ms != null && <span className="text-ink-3"> Computed in {Math.round(s.elapsed_ms)} ms, seed {s.seed}.</span>}
        </p>
      </div>

      <Tabs.Root defaultValue="explore" className="rounded-lg border border-rule bg-panel">
        <Tabs.List className="flex flex-wrap gap-1 border-b border-rule px-3 pt-2">
          {[['explore', 'Driver map'], ['drivers', 'What moves value'], ['cdf', 'Cumulative'], ['cash', 'Cash flows'], ['table', 'Base case'], ['diag', 'Diagnostics']].map(([v, l]) => (
            <Tabs.Trigger key={v} value={v} className="-mb-px border-b-2 border-transparent px-2.5 pb-2 text-[13px] text-ink-3 hover:text-ink data-[state=active]:border-ink data-[state=active]:font-medium data-[state=active]:text-ink">{l}</Tabs.Trigger>
          ))}
        </Tabs.List>
        <div className="p-4">
          <Tabs.Content value="explore"><Explorer s={s} specs={specs} currency={currency} runToken={runToken} savedId={savedId} /></Tabs.Content>
          <Tabs.Content value="drivers">
            <p className="mb-2 text-[13px] text-ink-2">Each bar moves one input from its own P10 to its P90 with everything else at base. Long bars are the assumptions worth researching; short ones can stay fixed. Teal: a higher input raises value; slate: a higher input lowers it.</p>
            <Tornado s={s} specs={specs} currency={currency} />
            <table className="mt-4 w-full text-[12.5px]">
              <thead className="text-left text-ink-3"><tr><th className="py-1 font-medium">Input</th><th className="py-1 text-right font-medium">Rank correlation with value</th><th className="py-1 text-right font-medium">Share of variance</th></tr></thead>
              <tbody>{s.sensitivity?.map(r => <tr key={r.key} className="border-t border-rule"><td className="py-1.5">{r.label}</td><td className="py-1.5 text-right tabular-nums">{fmtNum(r.rho, 2)}</td><td className="py-1.5 text-right tabular-nums">{fmtPct(r.contribution, 0)}</td></tr>)}</tbody>
            </table>
          </Tabs.Content>
          <Tabs.Content value="cdf"><p className="mb-2 text-[13px] text-ink-2">Read any price on the horizontal axis to see the share of futures in which the company is worth less.</p><CdfChart s={s} currency={currency} /></Tabs.Content>
          <Tabs.Content value="cash"><FanChart s={s} currency={currency} /></Tabs.Content>
          <Tabs.Content value="table"><BaseTable b={s.base} currency={currency} /></Tabs.Content>
          <Tabs.Content value="diag"><Diagnostics s={s} specs={specs} /></Tabs.Content>
        </div>
      </Tabs.Root>

      <div className="rounded-lg border border-rule bg-panel p-4">
        <h3 className="section-title">Valuation register</h3>
        {savedId ? (
          <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
            <p className="text-[13px] text-ink-2">Saved{savedAt && ` on ${fmtDate(savedAt)}`}. <Link className="text-value underline underline-offset-2" to={`/c/${ticker}`}>See {ticker}'s history</Link>. Editing an input and running again creates a new entry; this one stays as it is.</p>
            <a className="btn" href={`/api/valuations/${savedId}/export.xlsx`}><Download size={14} /> Excel report</a>
          </div>
        ) : (
          <div className="mt-2 grid gap-3 sm:grid-cols-[1fr_2fr_auto] sm:items-end">
            <label><span className="label">Label</span><input className="field mt-1" value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g. Post Q3 2026" /></label>
            <label><span className="label">Notes</span><input className="field mt-1" value={notes} onChange={e => setNotes(e.target.value)} placeholder="What changed and why" /></label>
            <button className="btn-primary h-8" disabled={saving || stale} onClick={onSave}>{saving ? <Spinner /> : <Save size={14} />} Save to register</button>
          </div>
        )}
        {saveError && <p className="mt-2 text-[12.5px] text-bad">{saveError}</p>}
        {stale && !savedId && <p className="hint mt-1">Run again before saving so the register keeps inputs and results that match.</p>}
      </div>
    </div>
  )
}

function Explorer({ s, specs, currency, runToken, savedId }: { s: Summary; specs: Record<string, ParamSpec>; currency: string; runToken: string | null; savedId: string | null }) {
  const keys = s.random_keys
  const top = s.sensitivity?.map(r => r.key) ?? keys
  const [x, setX] = useState(top[0] ?? '')
  const [y, setY] = useState(top[1] ?? '')
  const [mode, setMode] = useState<'value' | 'prob'>('prob')
  const preset = s.heatmaps?.find(h => h.x_key === x && h.y_key === y)
  const q = useQuery<Heatmap>({
    queryKey: ['explore', runToken, savedId, x, y], enabled: !!x && !!y && x !== y && !preset && !!(runToken || savedId),
    queryFn: () => api.explore({ x, y, run_token: runToken ?? undefined, valuation_id: runToken ? undefined : savedId ?? undefined }),
  })
  const h = preset ?? q.data
  if (keys.length === 0) return <p className="text-[13px] text-ink-2">No input has a distribution, so every path is the base case. Give the key drivers a distribution to map them.</p>
  if (keys.length === 1) return <ScatterExplorer s={s} xKey={keys[0]} spec={specs[keys[0]]} currency={currency} />
  return (
    <div>
      <p className="mb-3 text-[13px] text-ink-2">Every combination of two drivers that the simulation produced, grouped into equal-sized slices. Each cell shows {mode === 'prob' ? 'the share of paths in which the value exceeds the price' : 'the median value'} for that combination, with all other inputs varying as simulated.</p>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select className="field w-auto" value={x} onChange={e => setX(e.target.value)}>{keys.map(k => <option key={k} value={k}>{specs[k]?.label}</option>)}</select>
        <span className="text-[12px] text-ink-3">against</span>
        <select className="field w-auto" value={y} onChange={e => setY(e.target.value)}>{keys.map(k => <option key={k} value={k}>{specs[k]?.label}</option>)}</select>
        <div className="ml-auto"><Segmented value={mode} onChange={setMode} options={[{ value: 'prob', label: 'Chance above price' }, { value: 'value', label: 'Median value' }]} /></div>
      </div>
      {x === y ? <ScatterExplorer s={s} xKey={x} spec={specs[x]} currency={currency} />
        : h ? <HeatmapChart h={h} specs={specs} mode={mode} price={s.price} currency={currency} />
        : q.isError ? <p className="text-[13px] text-warn">{(q.error as Error).message}</p> : <div className="flex h-80 items-center justify-center"><Spinner /></div>}
      <details className="mt-3"><summary className="cursor-pointer text-[13px] text-ink-2">Scatter of value against {specs[x]?.label}</summary>
        <ScatterExplorer s={s} xKey={x} spec={specs[x]} currency={currency} /></details>
    </div>
  )
}

function BaseTable({ b, currency }: { b: BaseCase; currency: string }) {
  const t = b.table
  const rows: [string, number[], (v: number) => string][] = [
    ['NOPAT growth', t.growth, v => fmtPct(v, 1)], ['NOPAT', t.nopat, v => fmtNum(v, 0)], ['Reinvestment rate', t.reinvestment, v => fmtPct(v, 0)],
    ['Return on new capital', t.roic, v => fmtPct(v, 1)], ['FCFF', t.fcff, v => fmtNum(v, 0)], ['WACC', t.wacc, v => fmtPct(v, 2)],
    ['Discount factor', t.discount_factor, v => fmtNum(1 / v, 3)], ['PV of FCFF', t.pv_fcff, v => fmtNum(v, 0)],
  ]
  const exportCsv = () => {
    const lines = [['', ...t.year.map(y => `Year ${y}`)].join(','), ...rows.map(([l, a]) => [l, ...a].join(','))]
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'base_case.csv'; a.click()
  }
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-[12.5px] tabular-nums">
          <thead className="text-ink-3"><tr><th className="py-1 text-left font-medium">Money in m {currency}</th>{t.year.map(y => <th key={y} className="py-1 text-right font-medium">Y{y}</th>)}</tr></thead>
          <tbody>{rows.map(([l, a, f]) => <tr key={l} className="border-t border-rule"><td className="py-1.5 pr-3">{l}</td>{a.map((v, i) => <td key={i} className="py-1.5 text-right">{f(v)}</td>)}</tr>)}</tbody>
        </table>
      </div>
      <div className="mt-4 grid gap-x-8 gap-y-1 text-[13px] sm:grid-cols-2">
        {([['PV of explicit FCFF', b.pv_fcff], ['Terminal value (year N)', b.tv], ['PV of terminal value', b.pv_tv], ['Enterprise value', b.ev],
          ['+ Cash', b.bridge.cash], ['+ Non-operating assets', b.bridge.non_operating_assets], ['− Debt', b.bridge.debt], ['− Minorities, leases, pensions, options', (b.bridge.minority_interests ?? 0) + (b.bridge.lease_liabilities ?? 0) + (b.bridge.pension_deficit ?? 0) + (b.bridge.options_value ?? 0)],
          ['Equity value', b.equity], ['Shares (m)', b.bridge.shares]] as [string, number | null][]).map(([k, v]) => (
          <div key={k} className="flex justify-between border-b border-rule/60 py-1"><span className="text-ink-2">{k}</span><span className="tabular-nums">{fmtNum(v, 0)}</span></div>
        ))}
        <div className="flex justify-between py-1 font-semibold"><span>Value per share</span><span className="tabular-nums">{fmtMoney(b.value_per_share, currency)}</span></div>
      </div>
      <button className="btn mt-3" onClick={exportCsv}><Download size={14} /> Export table (CSV)</button>
    </div>
  )
}

function Diagnostics({ s, specs }: { s: Summary; specs: Record<string, ParamSpec> }) {
  const rel = s.sem && s.mean ? s.sem / Math.abs(s.mean) : null
  return (
    <div className="space-y-4 text-[13px]">
      <p className="text-ink-2">Standard error of the mean: <b className="text-ink">{fmtNum(s.sem)}</b>{rel != null && <> ({fmtPct(rel, 2)} of the mean)</>}. When both lines below flatten inside the dotted band, more paths won't change the answer.</p>
      <ConvergenceChart s={s} />
      <div className="grid gap-x-8 sm:grid-cols-2">
        <div className="flex justify-between border-b border-rule py-1"><span className="text-ink-2">Paths dropped (terminal spread)</span><span>{fmtPct(s.invalid_fraction, 2)}</span></div>
        <div className="flex justify-between border-b border-rule py-1"><span className="text-ink-2">Paths in distress</span><span>{fmtPct(s.failed_fraction, 2)}</span></div>
        <div className="flex justify-between border-b border-rule py-1"><span className="text-ink-2">Worst 5% average (CVaR)</span><span>{fmtNum(s.cvar5)}</span></div>
        <div className="flex justify-between border-b border-rule py-1"><span className="text-ink-2">Skew of value</span><span>{fmtNum(s.skew)}</span></div>
        <div className="flex justify-between border-b border-rule py-1"><span className="text-ink-2">Terminal value share P10–P90</span><span>{fmtPct(s.tv_share?.p10, 0)} – {fmtPct(s.tv_share?.p90, 0)}</span></div>
        <div className="flex justify-between border-b border-rule py-1"><span className="text-ink-2">WACC P10–P90</span><span>{fmtPct(s.wacc?.p10, 2)} – {fmtPct(s.wacc?.p90, 2)}</span></div>
      </div>
      {Object.keys(s.clipped).length > 0 && (
        <p className="text-warn">Draws clipped at their limits: {Object.entries(s.clipped).map(([k, v]) => `${specs[k]?.label ?? k} ${fmtPct(v, 1)}`).join(', ')}. Prefer a bounded shape for these inputs.</p>
      )}
      {s.inputs && (
        <table className="w-full text-[12.5px]">
          <thead className="text-left text-ink-3"><tr><th className="py-1 font-medium">Simulated input</th><th className="py-1 text-right font-medium">P5</th><th className="py-1 text-right font-medium">Median</th><th className="py-1 text-right font-medium">P95</th></tr></thead>
          <tbody>{Object.entries(s.inputs).map(([k, r]) => <tr key={k} className="border-t border-rule"><td className="py-1.5">{r.label}</td>{(['p5', 'p50', 'p95'] as const).map(q => <td key={q} className="py-1.5 text-right tabular-nums">{fmtUnit(r.unit, r[q])}</td>)}</tr>)}</tbody>
        </table>
      )}
    </div>
  )
}

function LegacyView({ v }: { v: { ticker: string; created_at: string; median: number | null; mean: number | null; price: number | null; prob_above_price: number | null; currency: string } }) {
  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <Empty title={`${v.ticker}: imported from the first version`} action={<Link className="btn" to={`/c/${v.ticker}`}>Back to history</Link>}>
        This run was saved by v1, which kept only rounded results, not the full inputs, so it can't be reopened in the workspace. Median {fmtNum(v.median)} {v.currency}, mean {fmtNum(v.mean)}, price {fmtNum(v.price)}, chance above price {fmtPct(v.prob_above_price, 0)} on {fmtDate(v.created_at)}.
      </Empty>
    </div>
  )
}
