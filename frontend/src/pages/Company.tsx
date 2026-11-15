import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { GitCompare, Plus, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { HistoryChart } from '../charts/charts'
import { Empty, Modal, RangeBar, Spinner } from '../components/ui'
import { api, type Inputs, type ParamSpec } from '../lib/api'
import { distLabel, fmtDate, fmtNum, fmtSignedPct, fmtUnit } from '../lib/format'
import { useMeta } from '../lib/meta'
import { ProbPill } from './Portfolio'

export default function Company() {
  const { ticker = '' } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { specs } = useMeta()
  const c = useQuery({ queryKey: ['company', ticker], queryFn: () => api.company(ticker) })
  const runs = useMemo(() => c.data?.valuations ?? [], [c.data])
  const first = runs[0]?.created_at
  const symbol = c.data?.yahoo_symbol
  const start = first ? new Date(new Date(first).getTime() - 180 * 864e5).toISOString().slice(0, 10) : '2020-01-01'
  const prices = useQuery({ queryKey: ['prices', symbol, start], queryFn: () => api.prices(symbol!, start), enabled: !!symbol, retry: false })
  const del = useMutation({ mutationFn: (id: string) => api.deleteValuation(id), onSuccess: () => { qc.invalidateQueries({ queryKey: ['company', ticker] }); qc.invalidateQueries({ queryKey: ['companies'] }) } })
  const [pick, setPick] = useState<string[]>([])
  const [cmp, setCmp] = useState(false)

  if (c.isLoading) return <div className="p-10"><Spinner /></div>
  if (!c.data) return <div className="mx-auto max-w-3xl p-10"><Empty title={`No valuations of ${ticker}`} action={<Link className="btn-primary" to={`/new?ticker=${ticker}`}>Value {ticker}</Link>} /></div>
  const cur = c.data.currency
  const lo = Math.min(...runs.map(r => Math.min(r.p10 ?? Infinity, r.price ?? Infinity))) * 0.92
  const hi = Math.max(...runs.map(r => Math.max(r.p90 ?? 0, r.price ?? 0))) * 1.05
  const latest = runs[runs.length - 1]
  const toggle = (id: string) => setPick(p => (p.includes(id) ? p.filter(x => x !== id) : [...p.slice(-1), id]))

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 lg:px-6">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[13px] text-ink-3"><Link to="/archive" className="hover:text-ink">Archive</Link> / {ticker}</p>
          <h1 className="text-[28px] font-semibold leading-tight">{c.data.name || ticker}</h1>
          <p className="mt-1 text-[14px] text-ink-2">{runs.length} valuation{runs.length === 1 ? '' : 's'} since {fmtDate(runs[0].created_at)}. Each mark is one run: the bar spans P10–P90 of intrinsic value, the dot is the median.{!symbol && ' Add a Yahoo symbol in the workspace to draw the price line.'}</p>
        </div>
        <div className="flex gap-2">
          {latest?.source !== 'legacy-import' && <Link className="btn" to={`/v/${latest.id}`}>Open latest</Link>}
          <Link className="btn-primary" to={`/v/${latest.id}`} onClick={e => { if (latest.source === 'legacy-import') { e.preventDefault(); nav(`/new?ticker=${ticker}&currency=${cur}`) } }}><Plus size={14} /> Revalue</Link>
        </div>
      </div>
      <div className="rounded-lg border border-rule bg-panel px-3 pt-3">
        <HistoryChart runs={runs} prices={prices.data ?? null} currency={cur} onSelect={id => nav(`/v/${id}`)} />
      </div>

      <div className="mt-6 flex items-center justify-between">
        <h2 className="section-title">Runs</h2>
        <button className="btn" disabled={pick.length !== 2} onClick={() => setCmp(true)}><GitCompare size={14} /> Compare selected ({pick.length}/2)</button>
      </div>
      <div className="mt-2 overflow-x-auto rounded-lg border border-rule bg-panel">
        <table className="w-full min-w-[900px] text-[13px]">
          <thead className="border-b border-rule text-left text-ink-3"><tr>
            <th className="w-8 px-3 py-2" /><th className="px-3 py-2 font-medium">Date</th><th className="px-3 py-2 font-medium">Label / notes</th>
            <th className="px-3 py-2 text-right font-medium">Price</th><th className="px-3 py-2 text-right font-medium">Base</th><th className="px-3 py-2 text-right font-medium">Median</th>
            <th className="px-3 py-2 text-right font-medium">Upside</th><th className="px-3 py-2 font-medium">P10 – P90</th><th className="px-3 py-2 text-right font-medium">Chance above price</th><th className="px-3 py-2" />
          </tr></thead>
          <tbody>
            {[...runs].reverse().map(r => (
              <tr key={r.id} className={clsx('border-t border-rule/70', pick.includes(r.id) && 'bg-value-soft/40')}>
                <td className="px-3"><input type="checkbox" aria-label="Select for comparison" checked={pick.includes(r.id)} onChange={() => toggle(r.id)} disabled={r.source === 'legacy-import'} /></td>
                <td className="px-3 py-2"><Link to={`/v/${r.id}`} className="hover:text-value">{fmtDate(r.created_at)}</Link>{r.source === 'legacy-import' && <span className="chip ml-1.5 bg-paper text-ink-3">v1</span>}</td>
                <td className="max-w-64 px-3 py-2"><p className="truncate">{r.label || <span className="text-ink-3">–</span>}</p>{r.notes && <p className="truncate text-[12px] text-ink-3">{r.notes}</p>}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmtNum(r.price)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmtNum(r.base_value)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{fmtNum(r.median)}</td>
                <td className={`px-3 py-2 text-right tabular-nums ${(r.upside_median ?? 0) >= 0 ? 'text-value' : 'text-market'}`}>{fmtSignedPct(r.upside_median)}</td>
                <td className="px-3 py-1"><RangeBar p10={r.p10} median={r.median} p90={r.p90} price={r.price} lo={lo} hi={hi} width={160} /></td>
                <td className="px-3 py-2 text-right"><ProbPill p={r.prob_above_price} /></td>
                <td className="px-3 py-2 text-right"><button className="btn-ghost" aria-label="Delete run" onClick={() => { if (confirm('Delete this valuation from the register? This cannot be undone.')) del.mutate(r.id) }}><Trash2 size={13} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {cmp && pick.length === 2 && <Compare ids={pick} specs={specs} onClose={() => setCmp(false)} />}
    </div>
  )
}

function Compare({ ids, specs, onClose }: { ids: string[]; specs: Record<string, ParamSpec>; onClose: () => void }) {
  const a = useQuery({ queryKey: ['valuation', ids[0]], queryFn: () => api.valuation(ids[0]) })
  const b = useQuery({ queryKey: ['valuation', ids[1]], queryFn: () => api.valuation(ids[1]) })
  const [A, B] = [a.data, b.data].sort((x, y) => (x && y ? +new Date(x.created_at) - +new Date(y.created_at) : 0))
  const keys = A && B ? Array.from(new Set([...Object.keys(A.inputs?.params ?? {}), ...Object.keys(B.inputs?.params ?? {})])).filter(k => specs[k]) : []
  const val = (i: Inputs | null | undefined, k: string) => i?.params[k]
  return (
    <Modal open onOpenChange={o => !o && onClose()} wide title="What changed between two runs" description="Inputs that differ are highlighted.">
      {!A || !B ? <Spinner /> : (
        <table className="w-full text-[13px]">
          <thead className="text-left text-ink-3"><tr><th className="py-1 font-medium">Input</th><th className="py-1 font-medium">{fmtDate(A.created_at)}</th><th className="py-1 font-medium">{fmtDate(B.created_at)}</th></tr></thead>
          <tbody>
            <tr className="border-t border-rule font-semibold"><td className="py-1.5">Median value</td><td>{fmtNum(A.median)}</td><td>{fmtNum(B.median)}</td></tr>
            {keys.map(k => {
              const pa = val(A.inputs, k), pb = val(B.inputs, k), sp = specs[k]
              const da = pa?.dist ? distLabel(pa.dist, sp) : 'Fixed', db = pb?.dist ? distLabel(pb.dist, sp) : 'Fixed'
              const diff = pa?.value !== pb?.value || da !== db
              return (
                <tr key={k} className={clsx('border-t border-rule', diff ? 'bg-warn-soft/50' : 'text-ink-3')}>
                  <td className="py-1.5 pr-2">{sp.label}</td>
                  <td className="py-1.5 pr-2">{fmtUnit(sp.unit, pa?.value)} <span className="text-[11.5px] text-ink-3">{da}</span></td>
                  <td className="py-1.5">{fmtUnit(sp.unit, pb?.value)} <span className="text-[11.5px] text-ink-3">{db}</span></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </Modal>
  )
}
