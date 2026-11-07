import { useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Empty, RangeBar, Spinner } from '../components/ui'
import { api, type CompanyRow } from '../lib/api'
import { fmtDate, fmtNum, fmtPct, fmtSignedPct } from '../lib/format'

type SortKey = 'prob' | 'upside' | 'ticker' | 'date'

export default function Portfolio() {
  const q = useQuery({ queryKey: ['companies'], queryFn: api.companies })
  const nav = useNavigate()
  const [sort, setSort] = useState<SortKey>('prob')
  const rows = useMemo(() => {
    const r = [...(q.data ?? [])]
    const by: Record<SortKey, (a: CompanyRow) => number | string> = {
      prob: a => -(a.latest.prob_above_price ?? -1), upside: a => -(a.latest.upside_median ?? -9),
      ticker: a => a.ticker, date: a => -new Date(a.latest.created_at).getTime(),
    }
    return r.sort((a, b) => (by[sort](a) < by[sort](b) ? -1 : 1))
  }, [q.data, sort])

  if (q.isLoading) return <div className="p-10"><Spinner /></div>
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 lg:px-6">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-semibold leading-tight">Valuation register</h1>
          <p className="mt-1 max-w-2xl text-[14px] text-ink-2">The latest simulation of every company you have valued. Teal bars span the 10th to 90th percentile of intrinsic value; the magenta tick is the price on the day of the run.</p>
        </div>
        <Link to="/new" className="btn-primary h-9"><Plus size={15} /> New valuation</Link>
      </div>
      {rows.length === 0 ? (
        <Empty title="No valuations yet" action={<Link to="/new" className="btn-primary">Start your first valuation</Link>}>
          Load a company tab from your Google Sheet or Excel template, or fetch its fundamentals from Yahoo Finance, then run and save the simulation. Each saved run appears here and in the company's history.
        </Empty>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-rule bg-panel">
          <table className="w-full min-w-[860px] text-[13px]">
            <thead className="border-b border-rule text-left text-ink-3">
              <tr>
                <Th onClick={() => setSort('ticker')} active={sort === 'ticker'}>Company</Th>
                <Th onClick={() => setSort('date')} active={sort === 'date'}>Last valued</Th>
                <th className="px-3 py-2 text-right font-medium">Price then</th>
                <th className="px-3 py-2 text-right font-medium">Median value</th>
                <Th onClick={() => setSort('upside')} active={sort === 'upside'} right>Upside</Th>
                <th className="px-3 py-2 font-medium">P10 – P90 vs price</th>
                <Th onClick={() => setSort('prob')} active={sort === 'prob'} right>Chance above price</Th>
                <th className="px-3 py-2 text-right font-medium">Runs</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(c => {
                const l = c.latest
                const lo = Math.min(l.p10 ?? 0, l.price ?? Infinity) * 0.92
                const hi = Math.max(l.p90 ?? 0, l.price ?? 0) * 1.05
                return (
                  <tr key={c.ticker} className="cursor-pointer border-t border-rule/70 hover:bg-paper" onClick={() => nav(`/c/${c.ticker}`)}>
                    <td className="px-3 py-2.5"><span className="font-semibold">{c.ticker}</span> <span className="text-ink-3">{c.name}</span></td>
                    <td className="px-3 py-2.5 text-ink-2">{fmtDate(l.created_at)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{fmtNum(l.price)} <span className="text-ink-3">{c.currency}</span></td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{fmtNum(l.median)}</td>
                    <td className={`px-3 py-2.5 text-right tabular-nums ${(l.upside_median ?? 0) >= 0 ? 'text-value' : 'text-market'}`}>{fmtSignedPct(l.upside_median)}</td>
                    <td className="px-3 py-1"><RangeBar p10={l.p10} median={l.median} p90={l.p90} price={l.price} lo={lo} hi={hi} /></td>
                    <td className="px-3 py-2.5 text-right"><ProbPill p={l.prob_above_price} /></td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-ink-2">{c.n_valuations}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Th({ children, onClick, active, right }: { children: React.ReactNode; onClick: () => void; active: boolean; right?: boolean }) {
  return <th className={`px-3 py-2 font-medium ${right ? 'text-right' : ''}`}><button onClick={onClick} className={active ? 'text-ink underline underline-offset-4' : 'hover:text-ink'}>{children}</button></th>
}

export function ProbPill({ p }: { p: number | null }) {
  if (p == null) return <span className="text-ink-3">–</span>
  const w = Math.round(p * 48)
  return (
    <span className="inline-flex items-center gap-2 tabular-nums">
      <span className="relative h-1.5 w-12 rounded-full bg-market-soft"><span className="absolute inset-y-0 left-0 rounded-full bg-value" style={{ width: w }} /></span>
      <span className={p >= 0.5 ? 'font-semibold text-value' : 'text-market'}>{fmtPct(p, 0)}</span>
    </span>
  )
}
