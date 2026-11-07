import * as Tabs from '@radix-ui/react-tabs'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { ChevronDown, CircleHelp, Dice5, Download, Plus, Save, SlidersHorizontal, Trash2, Upload } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
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

// Inputs the app works with. Anything else (from an import) is dropped so hidden values never move the result.
const FIN = ['price', 'shares', 'cash', 'ebit', 'debt', 'tax_rate'] as const
const GROWTH = ['growth_1', 'growth_2', 'reinvestment_1', 'reinvestment_2'] as const
const RISK = ['risk_free', 'erp', 'beta'] as const
const HIDDEN_KEEP = ['default_spread', 'debt_weight', 'terminal_roic', 'terminal_roic_spread']
const KEEP = new Set<string>([...FIN, ...GROWTH, ...RISK, ...HIDDEN_KEEP])

/** Fixes the model structure to the house method: build-up WACC, rate-based reinvestment,
 *  terminal growth = Rf and a mature-firm terminal WACC (Rf + ERP). Only terminal ROIC is a choice. */
function normalize(inp: Inputs): Inputs {
  const params: Inputs['params'] = {}
  for (const [k, p] of Object.entries(inp.params)) if (KEEP.has(k)) params[k] = p
  for (const k of FIN) if (params[k]?.dist) params[k] = { ...params[k], dist: { kind: 'fixed' } }
  return {
    ...inp, params, country_risk: [],
    model: { stage1_years: inp.model?.stage1_years ?? 5, stage2_years: inp.model?.stage2_years ?? 5, stage2_mode: inp.model?.stage2_mode ?? 'flat',
      reinvestment_mode: 'rate', discount_mode: 'build_up', wacc_fade: false, mid_year: false },
    terminal: { method: 'rf_linked', wacc_source: 'market', roic_mode: inp.terminal?.roic_mode ?? 'equal_wacc' },
  }
}

export default function Workspace() {
  const { id } = useParams()
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { meta, specs } = useMeta()
  const [inputs, setInputsRaw] = useState<Inputs | null>(null)
  const setInputs = useCallback((i: Inputs | null) => setInputsRaw(i ? normalize(i) : i), [])
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
  }, [id, saved.data, sp, setInputs])

  useEffect(() => { if (!id && inputs) localStorage.setItem(DRAFT, JSON.stringify({ inputs, ranges })) }, [inputs, ranges, id])

  // ---------------------------------------------------------------- live validation (base case + WACC spread)
  const [debounced, setDebounced] = useState(inputs)
  useEffect(() => { const t = setTimeout(() => setDebounced(inputs), 350); return () => clearTimeout(t) }, [inputs])
  const val = useQuery({ queryKey: ['validate', debounced], queryFn: () => api.validate(debounced!), enabled: !!debounced, placeholderData: p => p, retry: false })
  const issues: Issue[] = val.data?.issues ?? []
  const errors = issues.filter(i => i.severity === 'error')
  const base: BaseCase | null = val.data?.base ?? null

  const update = useCallback((fn: (d: Inputs) => Inputs) => { setInputsRaw(prev => (prev ? fn(structuredClone(prev)) : prev)); setDirtySinceRun(true) }, [])
  const setParam = (key: string, patch: Partial<ParamInput>) => update(d => {
    const cur = d.params[key] ?? { value: null }
    const next = { ...cur, ...patch }
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
      setInputs({ ...imp, simulation: { ...(inputs?.simulation ?? {}), ...(imp.simulation ?? {}) } })
    } else {
      update(d => {
        for (const [k, p] of Object.entries(imp.params)) if (KEEP.has(k)) d.params[k] = { ...(d.params[k] ?? {}), value: p.value, source: p.source, note: p.note ?? d.params[k]?.note }
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
  const issuesByParam: Record<string, Issue[]> = {}
  issues.forEach(i => { if (i.param) (issuesByParam[i.param] ??= []).push(i) })
  const randomKeys = [...GROWTH, ...RISK].filter(k => inputs.params[k]?.dist && inputs.params[k]!.dist!.kind !== 'fixed')
  const nopat = base?.nopat0 ?? null
  const cell = (k: string, opts: { fixed?: boolean } = {}) => (
    <Cell key={k} spec={specs[k]} p={inputs.params[k] ?? { value: null }} currency={cur} fixed={opts.fixed}
      issues={issuesByParam[k] ?? []} hasRange={!!ranges[k]}
      onValue={v => setParam(k, { value: v })} onDist={dist => setParam(k, { dist })} onEditDist={() => setEditing(k)} />
  )
  const stage2 = (model.stage2_years ?? 5) > 0 && model.stage2_mode !== 'fade'

  return (
    <div className="lg:flex">
      {/* ================================================= sidebar: inputs */}
      <aside className="side lg:sticky lg:top-12 lg:h-[calc(100vh-3rem)] lg:w-[460px] lg:shrink-0 lg:overflow-y-auto">
        <div className="space-y-5 px-4 pb-24 pt-4">
          <section>
            <div className="side-title">Company
              <div className="flex gap-1.5">
                <button className="side-btn" onClick={() => setImportOpen(true)}><Upload size={13} /> Load data</button>
                <button className="side-btn" onClick={() => { localStorage.removeItem(DRAFT); nav('/new?ticker=NEW'); window.location.reload() }}><Plus size={13} /> New</button>
              </div>
            </div>
            <div className="grid grid-cols-[90px_1fr_64px] gap-2">
              <label><span className="label">Ticker</span><input className="field mt-0.5 font-semibold uppercase" value={inputs.company.ticker} onChange={e => update(d => ({ ...d, company: { ...d.company, ticker: e.target.value.toUpperCase() } }))} /></label>
              <label><span className="label">Company name</span><input className="field mt-0.5" value={inputs.company.name ?? ''} onChange={e => update(d => ({ ...d, company: { ...d.company, name: e.target.value } }))} /></label>
              <label><span className="label">Currency</span><input className="field mt-0.5 uppercase" maxLength={3} value={inputs.company.currency} onChange={e => update(d => ({ ...d, company: { ...d.company, currency: e.target.value.toUpperCase() } }))} /></label>
            </div>
          </section>

          <section>
            <div className="side-title">Financial information <span className="text-[11px] font-normal text-on-navy-3">millions, except price</span></div>
            <div className="grid grid-cols-3 gap-x-2 gap-y-2">{FIN.map(k => cell(k, { fixed: true }))}</div>
            <p className="mt-2 text-[12px] text-on-navy-2">Implied NOPAT = EBIT × (1 − tax): <b className="text-on-navy">{fmtNum(nopat, 0)}m {cur}</b></p>
          </section>

          <section>
            <div className="side-title">Growth & reinvestment
              <span className="flex items-center gap-1 text-[11px] font-normal text-on-navy-3">value · std. dev.</span></div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-2">
              {cell('growth_1')}{stage2 ? cell('growth_2') : <FadeNote />}
              {cell('reinvestment_1')}{stage2 ? cell('reinvestment_2') : <FadeNote />}
            </div>
            <ImpliedRoic inputs={inputs} />
          </section>

          <section>
            <div className="side-title">Discount rate</div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-2">{RISK.map(k => cell(k))}</div>
            <WaccLine base={base} wacc={val.data?.wacc ?? null} />
          </section>

          <section>
            <div className="side-title">Model</div>
            <div className="space-y-2 text-[12.5px]">
              <div className="flex items-center justify-between gap-2"><span className="text-on-navy-2">Forecast years</span>
                <span className="flex items-center gap-1.5 text-on-navy-3">stage 1 <NumberField className="w-12" value={model.stage1_years ?? 5} onCommit={v => setModel({ stage1_years: Math.max(1, Math.round(v ?? 5)) })} />
                  stage 2 <NumberField className="w-12" value={model.stage2_years ?? 5} onCommit={v => setModel({ stage2_years: Math.max(0, Math.round(v ?? 5)) })} /></span></div>
              <div className="flex items-center justify-between gap-2"><Hint label="Stage 2" text="Own inputs: use the stage-2 growth and reinvestment. Fade: move linearly from stage 1 to the terminal values, so there is no cliff in the terminal year." />
                <Seg value={model.stage2_mode ?? 'flat'} onChange={v => setModel({ stage2_mode: v as Model['stage2_mode'] })} options={[['flat', 'Own inputs'], ['fade', 'Fade to terminal']]} /></div>
              <div className="flex items-center justify-between gap-2"><Hint label="Terminal ROIC" text="Terminal growth = Rf and terminal WACC = Rf + ERP (a mature firm). Terminal reinvestment = g / ROIC. ROIC = WACC means growth adds no value in perpetuity (conservative); a spread above WACC describes a lasting moat." />
                <Seg value={term.roic_mode ?? 'equal_wacc'} onChange={v => setTerm({ roic_mode: v as Term['roic_mode'] })} options={[['equal_wacc', '= WACC'], ['spread', 'WACC + spread'], ['absolute', 'Absolute']]} /></div>
              {term.roic_mode === 'spread' && <div className="grid grid-cols-2 gap-2">{cell('terminal_roic_spread', { fixed: true })}</div>}
              {term.roic_mode === 'absolute' && <div className="grid grid-cols-2 gap-2">{cell('terminal_roic', { fixed: true })}</div>}
            </div>
          </section>

          <SimPanel inputs={inputs} update={update} randomKeys={randomKeys} specs={specs} />
        </div>
        <div className="sticky bottom-0 border-t border-white/10 bg-navy-900/95 px-4 py-3 backdrop-blur">
          <button className="flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-run text-[14px] font-semibold text-white shadow-[0_10px_22px_rgba(22,163,74,.25)] hover:brightness-110 disabled:opacity-60"
            disabled={errors.length > 0 || sim.isPending} onClick={() => sim.mutate()}>
            {sim.isPending ? <Spinner /> : <Dice5 size={16} />} Run simulation · {(inputs.simulation?.n ?? 20000).toLocaleString('en-US')} paths
          </button>
          {errors.length > 0 && <p className="mt-1.5 text-center text-[11.5px] text-on-navy-2">Fix the inputs marked in red to run.</p>}
        </div>
      </aside>

      {/* ================================================= results */}
      <main className="min-w-0 flex-1 space-y-5 bg-white px-4 py-5 lg:px-8">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="text-[24px] font-semibold">{inputs.company.name || inputs.company.ticker}<span className="ml-2 text-[15px] font-normal text-ink-3">{inputs.company.ticker} · {cur}</span></h1>
          <BaseInline base={base} currency={cur} />
        </div>
        <IssueList issues={visibleIssues(issues)} />
        {simErr && <p className="rounded-md bg-bad-soft px-3 py-2 text-[13px] text-bad">{simErr}</p>}
        {summary?.histogram ? (
          <Results s={summary} specs={specs} currency={cur} runToken={runToken} savedId={savedId} stale={dirtySinceRun}
            savedAt={savedAt} label={label} notes={notes} setLabel={setLabel} setNotes={setNotes} inputs={inputs}
            onSave={() => save.mutate()} saving={save.isPending} saveError={save.error?.message ?? null} ticker={inputs.company.ticker} />
        ) : (
          <Empty title="Run the simulation to see the results">
            Fill in the inputs on the left (or load them with "Load data"), give the uncertain ones a standard deviation, and press "Run simulation".
          </Empty>
        )}
      </main>

      {editing && specs[editing] && (
        <DistEditor open onOpenChange={o => !o && setEditing(null)} spec={specs[editing]} param={inputs.params[editing] ?? { value: null }}
          range={ranges[editing]} onApply={dist => setParam(editing, { dist })} />
      )}
      <ImportDialog open={importOpen} onOpenChange={setImportOpen} onApply={onImport} defaultSymbol={inputs.company.yahoo_symbol ?? undefined} />
    </div>
  )
}

function visibleIssues(issues: Issue[]): Issue[] {
  const shown = issues.filter(i => i.severity !== 'info')
  const missing = shown.filter(i => i.code === 'missing')
  if (missing.length <= 2) return shown
  return [{ severity: 'error', code: 'missing_many', message: `${missing.length} inputs still need a value; they are marked in red on the left. Load a template tab or type them in.` },
    ...shown.filter(i => i.code !== 'missing')]
}

const FadeNote = () => <div className="self-end pb-1 text-[11.5px] text-on-navy-3">Stage 2 fades to terminal</div>

function Hint({ label, text }: { label: string; text: string }) {
  return <span className="flex items-center gap-1 text-on-navy-2">{label}<Tip content={text}><button aria-label="Help" className="text-on-navy-3 hover:text-on-navy"><CircleHelp size={12} /></button></Tip></span>
}

function Seg({ value, options, onChange }: { value: string; options: [string, string][]; onChange: (v: string) => void }) {
  return <div className="side-seg" role="radiogroup">{options.map(([v, l]) => <button key={v} role="radio" aria-checked={value === v} onClick={() => onChange(v)}>{l}</button>)}</div>
}

const SIGMA_KINDS = new Set(['fixed', 'normal', 'truncnormal', 'student_t'])

/** One input: label, value and (for uncertain inputs) its standard deviation, with the full shape editor one click away. */
function Cell({ spec, p, currency, fixed, issues, hasRange, onValue, onDist, onEditDist }: {
  spec: ParamSpec; p: ParamInput; currency: string; fixed?: boolean; issues: Issue[]; hasRange: boolean
  onValue: (v: number | null) => void; onDist: (d: Dist) => void; onEditDist: () => void
}) {
  if (!spec) return null
  const err = issues.some(i => i.severity === 'error')
  const pct = isPct(spec.unit)
  const suffix = pct ? '%' : spec.unit === 'price' ? currency : ''
  const d = p.dist ?? { kind: 'fixed' }
  const sd = typeof d.sd === 'number' ? (d.sd as number) : null
  const simple = SIGMA_KINDS.has(d.kind)
  const setSigma = (v: number | null) => {
    const s = v == null ? 0 : Math.abs(pct ? v / 100 : v)
    if (!s) return onDist({ kind: 'fixed' })
    if (d.kind === 'truncnormal' || d.kind === 'student_t') return onDist({ ...d, sd: s })
    onDist({ kind: 'normal', mean: p.value ?? 0, sd: s })
  }
  const tip = <><p className="font-medium text-ink">{spec.label}</p><p className="mt-1">{spec.description}</p>{spec.help && <p className="mt-1">{spec.help}</p>}
    {p.source && p.source !== 'manual' && <p className="mt-1 text-ink-3">Source: {p.source}</p>}
    {issues.map((i, k) => <p key={k} className={clsx('mt-1', i.severity === 'error' ? 'text-bad' : 'text-warn')}>{i.message}</p>)}</>
  return (
    <div id={`param-${spec.key}`} className="min-w-0">
      <Tip content={tip} side="right">
        <span className={clsx('label block truncate', err && '!text-[#ffb4ab]')}>{spec.label.replace(' (mature)', '').replace(', stage ', ' ').replace('Shares outstanding (diluted)', 'Shares (diluted)').replace('Base operating income (EBIT)', 'Operating income (EBIT)').replace('Market price', 'Current price')}
          {issues.some(i => i.severity === 'warning') && !err && <span className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-[#f5b942] align-middle" />}</span>
      </Tip>
      <div className="mt-0.5 flex gap-1">
        <NumberField className="min-w-0 flex-1" value={toDisplay(spec.unit, p.value ?? null)} suffix={suffix} invalid={err} ariaLabel={spec.label}
          onCommit={v => onValue(v == null ? null : pct ? v / 100 : v)} />
        {!fixed && (simple
          ? <NumberField className="w-[64px] shrink-0" value={sd == null ? null : +(pct ? sd * 100 : sd).toPrecision(3)} placeholder="± σ" ariaLabel={`${spec.label} standard deviation`} onCommit={setSigma} />
          : <button onClick={onEditDist} title={distLabel(d, spec)} className="h-7 w-[64px] shrink-0 truncate rounded-md bg-cyan/90 px-1 text-[11px] font-semibold text-navy-950 hover:bg-cyan">{d.kind === 'lognormal' ? 'LogN' : d.kind === 'truncnormal' ? 'TruncN' : d.kind.toUpperCase().slice(0, 6)}</button>)}
        {!fixed && <button onClick={onEditDist} aria-label={`Shape of ${spec.label}`} title={hasRange ? 'Choose a shape (your notes have a range for this input)' : 'Choose a shape, with suggestions'}
          className={clsx('flex h-7 w-6 shrink-0 items-center justify-center rounded-md hover:bg-white/15', hasRange ? 'text-cyan' : 'text-on-navy-3')}><SlidersHorizontal size={13} /></button>}
      </div>
    </div>
  )
}

function ImpliedRoic({ inputs }: { inputs: Inputs }) {
  const r = (g?: number | null, rr?: number | null) => (g != null && rr ? g / rr : null)
  const a = r(inputs.params.growth_1?.value, inputs.params.reinvestment_1?.value)
  const b = r(inputs.params.growth_2?.value, inputs.params.reinvestment_2?.value)
  return <p className="mt-2 text-[12px] text-on-navy-2">Implied return on new capital (g / reinvestment): <b className="text-on-navy">{fmtPct(a, 1)}</b> stage 1 · <b className="text-on-navy">{fmtPct(b, 1)}</b> stage 2</p>
}

function WaccLine({ base, wacc }: { base: BaseCase | null; wacc: { mean: number; sd: number; p5: number; p95: number } | null }) {
  return (
    <div className="mt-2 rounded-md bg-navy-950/50 px-3 py-2 text-[12.5px]">
      <div className="flex items-baseline justify-between"><span className="text-on-navy-2">WACC</span>
        <span className="text-[15px] font-semibold text-on-navy">{fmtPct(base?.wacc, 2)}{wacc && <span className="ml-1 text-[12.5px] font-normal text-on-navy-2">± {fmtPct(wacc.sd, 2)}</span>}</span></div>
      {wacc && <div className="mt-0.5 flex justify-between text-[11.5px] text-on-navy-3"><span>90% range from Rf, ERP and beta</span><span>{fmtPct(wacc.p5, 2)} – {fmtPct(wacc.p95, 2)}</span></div>}
      <div className="mt-0.5 flex justify-between text-[11.5px] text-on-navy-3"><span>Terminal: g = Rf · WACC = Rf + ERP</span><span>{fmtPct(base?.growth_terminal, 2)} · {fmtPct(base?.wacc_terminal, 2)}</span></div>
    </div>
  )
}

function SimPanel({ inputs, update, randomKeys, specs }: { inputs: Inputs; update: (fn: (d: Inputs) => Inputs) => void; randomKeys: string[]; specs: Record<string, ParamSpec> }) {
  const sim = inputs.simulation ?? {}
  const corr = sim.correlations ?? []
  const setSim = (patch: Partial<NonNullable<Inputs['simulation']>>) => update(d => ({ ...d, simulation: { ...d.simulation, ...patch } }))
  return (
    <section>
      <div className="side-title">Simulation</div>
      <div className="grid grid-cols-2 gap-2">
        <label><span className="label">Paths</span><NumberField className="mt-0.5" value={sim.n ?? 20000} onCommit={v => setSim({ n: Math.min(2_000_000, Math.max(100, Math.round(v ?? 20000))) })} /></label>
        <label><span className="label">Random seed (optional)</span><NumberField className="mt-0.5" value={sim.seed ?? null} placeholder="random" onCommit={v => setSim({ seed: v == null ? null : Math.round(v) })} /></label>
      </div>
      <details className="group mt-3">
        <summary className="flex cursor-pointer list-none items-center gap-1 text-[12.5px] text-on-navy-2 hover:text-on-navy"><ChevronDown size={13} className="transition-transform group-open:rotate-180" /> Correlations between inputs {corr.length > 0 && `(${corr.length})`}</summary>
        <p className="hint mt-1">Inputs that move together (e.g. growth and reinvestment). Damodaran used 0.5 between Apple's growth and margin.</p>
        {corr.map((c, i) => (
          <div key={i} className="mt-1.5 grid grid-cols-[1fr_1fr_56px_24px] items-center gap-1.5">
            {(['a', 'b'] as const).map(side => (
              <select key={side} className="field" value={c[side]} onChange={e => update(d => { d.simulation!.correlations![i][side] = e.target.value; return d })}>
                {randomKeys.map(k => <option key={k} value={k}>{specs[k]?.label}</option>)}
              </select>
            ))}
            <NumberField value={c.rho} onCommit={v => update(d => { d.simulation!.correlations![i].rho = Math.max(-0.99, Math.min(0.99, v ?? 0)); return d })} />
            <button className="text-on-navy-3 hover:text-on-navy" aria-label="Remove" onClick={() => update(d => { d.simulation!.correlations!.splice(i, 1); return d })}><Trash2 size={13} /></button>
          </div>
        ))}
        <button className="side-btn mt-2" disabled={randomKeys.length < 2} onClick={() => update(d => ({ ...d, simulation: { ...d.simulation, correlations: [...corr, { a: randomKeys[0], b: randomKeys[1], rho: 0.5 }] } }))}><Plus size={12} /> Add correlation</button>
        {randomKeys.length < 2 && <p className="hint mt-1">Give at least two inputs a standard deviation first.</p>}
      </details>
    </section>
  )
}

function BaseInline({ base, currency }: { base: BaseCase | null; currency: string }) {
  if (!base?.value_per_share) return null
  return <p className="text-[13px] text-ink-2">Base case <b className="text-ink">{fmtNum(base.value_per_share)} {currency}</b> <span className={(base.upside ?? 0) >= 0 ? 'text-good' : 'text-bad'}>({fmtSignedPct(base.upside)} vs price)</span> · terminal value {fmtPct(base.tv_share, 0)} of EV</p>
}

function Kv({ k, v, accent }: { k: string; v: string; accent?: string }) {
  return <div><p className="label">{k}</p><p className={clsx('mt-0.5 text-[17px] font-semibold tabular-nums', accent)}>{v}</p></div>
}

/** The valuation summary report, as in v1. */
function SummaryReport({ s, inputs, specs, currency }: { s: Summary; inputs: Inputs; specs: Record<string, ParamSpec>; currency: string }) {
  const p = s.percentiles!
  const prob = s.prob_above_price ?? 0
  const row = (k: string, v: string) => <div className="flex justify-between gap-3 py-[3px]"><span className="text-ink-2">{k}</span><span className="tabular-nums font-medium">{v}</span></div>
  const varKeys = [...GROWTH, ...RISK].filter(k => inputs.params[k])
  const date = new Date().toISOString().slice(0, 10)
  return (
    <div className="card p-4 text-[12.5px]">
      <p className="text-center font-cond text-[14px] font-semibold">Valuation summary · {inputs.company.ticker}</p>
      <p className="mb-2 text-center text-[11.5px] text-ink-3">{date}</p>
      <div className="grid gap-x-6 sm:grid-cols-2">
        <div>
          {row('Current price', fmtMoney(s.price, currency))}
          {row('Mean value', fmtMoney(s.mean, currency))}
          {row('Median value', fmtMoney(s.median, currency))}
          {row('Upside potential (mean)', fmtSignedPct(s.upside_mean, 1))}
          <p className="mt-2 font-semibold">Probabilities</p>
          {row('Overvaluation', fmtPct(1 - prob, 1))}
          {row('Undervaluation', fmtPct(prob, 1))}
          <p className="mt-2 font-semibold">Risk metrics</p>
          {row('VaR 95% (P5 value)', fmtMoney(p.p5, currency))}
          {row('CVaR 95% (avg. worst 5%)', fmtMoney(s.cvar5, currency))}
          {row('Std. deviation', fmtMoney(s.sd, currency))}
        </div>
        <div>
          <p className="mt-2 font-semibold sm:mt-0">Variable parameters</p>
          {varKeys.map(k => {
            const sp = specs[k], q = inputs.params[k]!
            const sd = s.inputs?.[k]?.sd
            return <div key={k}>{row(sp.label.replace(' (mature)', ''), `${fmtUnit(sp.unit, q.value)}${sd ? ` (±${fmtUnit(sp.unit, sd)})` : ''}`)}</div>
          })}
          {row('WACC (simulated)', `${fmtPct(s.wacc?.p50, 2)} (${fmtPct(s.wacc?.p5, 1)}–${fmtPct(s.wacc?.p95, 1)})`)}
          <p className="mt-2 font-semibold">Terminal value params</p>
          {row('Term. growth', fmtPct(s.base.growth_terminal, 2))}
          {row('Term. WACC', fmtPct(s.base.wacc_terminal, 2))}
          {row('Term. reinvestment rate', fmtPct(s.base.reinvestment_terminal, 2))}
        </div>
      </div>
    </div>
  )
}

function Results({ s, specs, currency, runToken, savedId, savedAt, stale, label, notes, setLabel, setNotes, onSave, saving, saveError, ticker, inputs }: {
  s: Summary; specs: Record<string, ParamSpec>; currency: string; runToken: string | null; savedId: string | null; savedAt: string | null
  stale: boolean; label: string; notes: string; setLabel: (v: string) => void; setNotes: (v: string) => void
  onSave: () => void; saving: boolean; saveError: string | null; ticker: string; inputs: Inputs
}) {
  const p = s.percentiles!
  const prob = s.prob_above_price ?? 0
  return (
    <div className="space-y-5">
      {stale && <p className="rounded-md bg-warn-soft px-3 py-2 text-[12.5px] text-warn">Inputs changed since this run. Run again to update the results.</p>}
      <div className="card flex flex-wrap items-end gap-x-8 gap-y-3 px-5 py-4">
        <div>
          <p className="label">Probability the value exceeds the price</p>
          <p className={clsx('font-cond text-[40px] font-semibold leading-none', prob >= 0.5 ? 'text-good' : 'text-bad')}>{fmtPct(prob, 0)}</p>
        </div>
        <Kv k={`Mean value (${currency})`} v={`${fmtNum(s.mean)}`} />
        <Kv k="Median" v={fmtNum(s.median)} />
        <Kv k="Upside (mean)" v={fmtSignedPct(s.upside_mean, 1)} accent={(s.upside_mean ?? 0) >= 0 ? 'text-good' : 'text-bad'} />
        <Kv k="P10 – P90" v={`${fmtNum(p.p10)} – ${fmtNum(p.p90)}`} />
        <Kv k="Current price" v={fmtNum(s.price)} />
      </div>

      <div className="grid gap-5 2xl:grid-cols-[1.35fr_1fr]">
        <div className="card px-3 pt-3">
          <p className="px-2 font-cond text-[14px] font-semibold">Intrinsic value distribution</p>
          <ValueField s={s} currency={currency} />
        </div>
        <SummaryReport s={s} inputs={inputs} specs={specs} currency={currency} />
      </div>
      <div className="grid gap-5 2xl:grid-cols-2">
        <div className="card px-3 pt-3">
          <p className="px-2 font-cond text-[14px] font-semibold">Free cash flow projection</p>
          <FanChart s={s} currency={currency} />
        </div>
        <div className="card px-3 pt-3">
          <p className="px-2 font-cond text-[14px] font-semibold">Sensitivity analysis</p>
          <p className="px-2 text-[12px] text-ink-3">Each bar moves one input from its P10 to its P90, the rest at base.</p>
          <Tornado s={s} specs={specs} currency={currency} />
        </div>
      </div>
      <p className="text-[12px] text-ink-3">{s.n_valid.toLocaleString('en-US')} valid paths{s.invalid_fraction > 0 && ` (${fmtPct(s.invalid_fraction, 1)} dropped: terminal WACC too close to growth)`}{s.elapsed_ms != null && ` · computed in ${Math.round(s.elapsed_ms)} ms · seed ${s.seed}`}.</p>

      <Tabs.Root defaultValue="explore" className="card">
        <Tabs.List className="flex flex-wrap gap-1 border-b border-rule px-3 pt-2">
          {[['explore', 'Driver map'], ['cdf', 'Cumulative'], ['table', 'Base case'], ['diag', 'Diagnostics']].map(([v, l]) => (
            <Tabs.Trigger key={v} value={v} className="-mb-px border-b-2 border-transparent px-2.5 pb-2 text-[13px] text-ink-3 hover:text-ink data-[state=active]:border-ink data-[state=active]:font-medium data-[state=active]:text-ink">{l}</Tabs.Trigger>
          ))}
        </Tabs.List>
        <div className="p-4">
          <Tabs.Content value="explore"><Explorer s={s} specs={specs} currency={currency} runToken={runToken} savedId={savedId} /></Tabs.Content>
          <Tabs.Content value="cdf"><p className="mb-2 text-[13px] text-ink-2">Read any price on the horizontal axis to see the share of outcomes in which the company is worth less.</p><CdfChart s={s} currency={currency} /></Tabs.Content>
          <Tabs.Content value="table"><BaseTable b={s.base} currency={currency} /></Tabs.Content>
          <Tabs.Content value="diag"><Diagnostics s={s} specs={specs} /></Tabs.Content>
        </div>
      </Tabs.Root>

      <div className="card p-4">
        <h3 className="section-title">Save to your register</h3>
        {savedId ? (
          <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
            <p className="text-[13px] text-ink-2">Saved{savedAt && ` on ${fmtDate(savedAt)}`}. <Link className="text-value underline underline-offset-2" to={`/c/${ticker}`}>See {ticker}'s history</Link>.</p>
            <a className="btn" href={`/api/valuations/${savedId}/export.xlsx`}><Download size={14} /> Excel report</a>
          </div>
        ) : (
          <div className="mt-2 grid gap-3 sm:grid-cols-[1fr_2fr_auto] sm:items-end">
            <label><span className="label">Label</span><input className="field mt-1" value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g. Post Q3 2026" /></label>
            <label><span className="label">Notes</span><input className="field mt-1" value={notes} onChange={e => setNotes(e.target.value)} placeholder="What changed and why" /></label>
            <button className="btn-primary h-8" disabled={saving || stale} onClick={onSave}>{saving ? <Spinner /> : <Save size={14} />} Save</button>
          </div>
        )}
        {saveError && <p className="mt-2 text-[12.5px] text-bad">{saveError}</p>}
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
          ['+ Cash', b.bridge.cash], ['− Debt', b.bridge.debt],
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
