import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Save, Trash2, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { NumberField, Spinner } from '../components/ui'
import { api } from '../lib/api'

export default function Settings() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const [rf, setRf] = useState<[string, number][]>([])
  const [erp, setErp] = useState<number | null>(null)
  const [paths, setPaths] = useState<number | null>(null)
  useEffect(() => {
    if (!q.data) return
    setRf(Object.entries((q.data.risk_free as Record<string, number>) ?? {}))
    setErp(q.data.erp_mature as number); setPaths(q.data.simulation_paths as number)
  }, [q.data])
  const save = useMutation({ mutationFn: () => api.putSettings({ risk_free: Object.fromEntries(rf.filter(([c]) => c)), erp_mature: erp, simulation_paths: paths }), onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }) })
  if (!q.data) return <div className="p-10"><Spinner /></div>
  return (
    <div className="mx-auto max-w-3xl px-4 py-8 lg:px-6">
      <h1 className="text-[28px] font-semibold">House assumptions</h1>
      <p className="mt-1 text-[14px] text-ink-2">Defaults for every new valuation, so the register stays comparable across companies. Imported sheets keep their own values.</p>
      <section className="mt-6">
        <h2 className="section-title border-b border-rule pb-1.5">Risk-free rate by currency</h2>
        <p className="hint mt-2">Long-term government bond yield in each currency (minus any sovereign default spread).</p>
        <div className="mt-2 space-y-1.5">
          {rf.map(([c, v], i) => (
            <div key={i} className="grid grid-cols-[90px_120px_32px] items-center gap-2">
              <input className="field uppercase" maxLength={3} value={c} onChange={e => setRf(r => r.map((x, j) => (j === i ? [e.target.value.toUpperCase(), x[1]] : x)))} />
              <NumberField value={v * 100} suffix="%" onCommit={n => setRf(r => r.map((x, j) => (j === i ? [x[0], (n ?? 0) / 100] : x)))} />
              <button className="btn-ghost" aria-label="Remove" onClick={() => setRf(r => r.filter((_, j) => j !== i))}><Trash2 size={13} /></button>
            </div>
          ))}
          <button className="btn-ghost" onClick={() => setRf(r => [...r, ['', 0.03]])}><Plus size={13} /> Add currency</button>
        </div>
      </section>
      <section className="mt-6 grid gap-4 sm:grid-cols-2">
        <label><span className="label">Mature-market equity risk premium</span><NumberField className="mt-1 w-32" value={erp == null ? null : erp * 100} suffix="%" onCommit={n => setErp(n == null ? null : n / 100)} /></label>
        <label><span className="label">Default simulation paths</span><NumberField className="mt-1 w-32" value={paths} onCommit={n => setPaths(n == null ? null : Math.round(n))} /></label>
      </section>
      <button className="btn-primary mt-6" onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? <Spinner /> : <Save size={14} />} Save defaults</button>
      {save.isSuccess && <span className="ml-3 text-[13px] text-good">Defaults saved.</span>}
      <LegacyImport />
    </div>
  )
}

function LegacyImport() {
  const qc = useQueryClient()
  const m = useMutation({ mutationFn: (f: File) => api.importLegacy(f), onSuccess: () => qc.invalidateQueries({ queryKey: ['companies'] }) })
  return (
    <section className="mt-10">
      <h2 className="section-title border-b border-rule pb-1.5">Bring in valuations from the first version</h2>
      <p className="hint mt-2">In the old Streamlit app, open "Export / Import Analyses" and download the ZIP, then upload it here. The runs appear in each company's history with their results; v1 didn't keep the full inputs, so they can't be reopened in the workspace.</p>
      <label className="btn mt-3 cursor-pointer"><Upload size={14} /> Upload v1 export (.zip)
        <input type="file" accept=".zip" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) m.mutate(f) }} />
      </label>
      {m.isPending && <Spinner className="ml-3" />}
      {m.data && <span className="ml-3 text-[13px] text-good">Imported {m.data.imported} valuation{m.data.imported === 1 ? '' : 's'}{m.data.skipped ? `, skipped ${m.data.skipped} already present` : ''}.</span>}
      {m.error && <span className="ml-3 text-[13px] text-bad">{(m.error as Error).message}</span>}
    </section>
  )
}
