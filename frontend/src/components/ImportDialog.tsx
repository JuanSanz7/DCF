import { clsx } from 'clsx'
import { CheckCircle2, FileSpreadsheet, Globe, Search, XCircle } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, type ImportResponse, type Inputs } from '../lib/api'
import { fmtUnit } from '../lib/format'
import { useMeta } from '../lib/meta'
import { Modal, Segmented, Spinner } from './ui'

type Source = 'sheet' | 'excel' | 'yahoo'
const LAST_SHEET = 'dcf:lastSheetUrl'
const LAST_TAB = 'dcf:lastSheetTab'

export function ImportDialog({ open, onOpenChange, onApply, defaultSymbol }: {
  open: boolean; onOpenChange: (o: boolean) => void; defaultSymbol?: string
  onApply: (inputs: Inputs, mode: 'replace' | 'merge', ranges: Record<string, [number, number]>) => void
}) {
  const { specs } = useMeta()
  const [src, setSrc] = useState<Source>('sheet')
  const [url, setUrl] = useState(() => localStorage.getItem(LAST_SHEET) ?? '')
  const [tabs, setTabs] = useState<string[]>([])
  const [tab, setTab] = useState(() => localStorage.getItem(LAST_TAB) ?? '')
  const [withNotes, setWithNotes] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [symbol, setSymbol] = useState(defaultSymbol ?? '')
  const [hits, setHits] = useState<{ symbol: string; name: string; exchange: string }[]>([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [res, setRes] = useState<ImportResponse | null>(null)

  useEffect(() => { if (open) { setRes(null); setErr(null); if (defaultSymbol) setSymbol(defaultSymbol) } }, [open, defaultSymbol])

  const run = async (fn: () => Promise<void>) => { setBusy(true); setErr(null); try { await fn() } catch (e) { setErr((e as Error).message) } finally { setBusy(false) } }
  const loadTabs = () => run(async () => { const r = await api.sheetTabs(url); setTabs(r.tabs); localStorage.setItem(LAST_SHEET, url) })
  const readSheet = () => run(async () => { setRes(await api.importSheet(url, tab.trim() || undefined, withNotes)); localStorage.setItem(LAST_SHEET, url); localStorage.setItem(LAST_TAB, tab.trim()) })
  const readExcel = (f: File, t?: string) => run(async () => {
    const r = await api.importExcel(f, t)
    if (r.needs_tab) { setTabs(r.tabs ?? []); setRes(null) } else setRes(r)
  })
  const readYahoo = (s: string) => run(async () => { setRes(await api.importYahoo(s)) })
  const search = () => run(async () => setHits(await api.searchTickers(symbol)))

  const ranges: Record<string, [number, number]> = {}
  if (res) Object.entries(res.import.fields).forEach(([k, f]) => { if (f.range) ranges[k] = f.range })

  return (
    <Modal open={open} onOpenChange={onOpenChange} wide title="Load company data"
      description="Read a tab of your valuation template (Google Sheets or Excel), or pull fundamentals from Yahoo Finance.">
      <Segmented value={src} onChange={v => { setSrc(v); setRes(null); setTabs([]); setErr(null) }} options={[
        { value: 'sheet', label: 'Google Sheet' }, { value: 'excel', label: 'Excel file' }, { value: 'yahoo', label: 'Yahoo Finance' }]} />

      <div className="mt-4 space-y-3">
        {src === 'sheet' && (
          <>
            <label className="block"><span className="label">Spreadsheet link</span>
              <input className="field mt-1" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://docs.google.com/spreadsheets/d/…" /></label>
            <label className="block"><span className="label">Tab name (exactly as in the sheet)</span>
              <div className="mt-1 flex gap-2">
                <input className="field max-w-48 font-semibold" value={tab} onChange={e => setTab(e.target.value)} placeholder="e.g. GOOGL" onKeyDown={e => e.key === 'Enter' && url && tab && readSheet()} />
                <button className="btn-primary shrink-0" onClick={readSheet} disabled={!url || !tab.trim() || busy}>{busy ? <Spinner /> : <Globe size={14} />} Read tab</button>
                <button className="btn-ghost shrink-0" onClick={loadTabs} disabled={!url || busy} title="Downloads the whole spreadsheet; can be slow">Show all tabs</button>
              </div>
            </label>
            {tabs.length > 0 && <TabPicker tabs={tabs} tab={tab} setTab={setTab} />}
            <label className="flex items-start gap-2 text-[12.5px] text-ink-2">
              <input type="checkbox" className="mt-0.5" checked={withNotes} onChange={e => setWithNotes(e.target.checked)} />
              <span>Also read the ranges written in cell notes (e.g. "RANGO: 70% - 110%") and turn them into suggested distributions. Slower: it downloads the whole spreadsheet.</span>
            </label>
            <p className="hint">The spreadsheet must be shared as "Anyone with the link: Viewer".</p>
          </>
        )}
        {src === 'excel' && (
          <>
            <label className="block"><span className="label">Workbook (.xlsx)</span>
              <input type="file" accept=".xlsx,.xlsm" className="mt-1 block text-[13px]" onChange={e => { const f = e.target.files?.[0] ?? null; setFile(f); setTab(''); if (f) readExcel(f) }} />
            </label>
            {tabs.length > 0 && <TabPicker tabs={tabs} tab={tab} setTab={t => { setTab(t); if (file) readExcel(file, t) }} />}
          </>
        )}
        {src === 'yahoo' && (
          <>
            <label className="block"><span className="label">Yahoo symbol</span>
              <div className="mt-1 flex gap-2">
                <input className="field" value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())} placeholder="GOOGL, ASML.AS, NOVO-B.CO" onKeyDown={e => e.key === 'Enter' && readYahoo(symbol)} />
                <button className="btn shrink-0" onClick={search} disabled={!symbol || busy}><Search size={14} /> Search</button>
                <button className="btn-primary shrink-0" onClick={() => readYahoo(symbol)} disabled={!symbol || busy}>{busy ? <Spinner /> : null} Fetch</button>
              </div>
            </label>
            {hits.length > 0 && (
              <ul className="max-h-40 overflow-y-auto rounded-md border border-rule text-[13px]">
                {hits.map(h => (
                  <li key={h.symbol}><button className="flex w-full justify-between px-3 py-1.5 text-left hover:bg-paper" onClick={() => { setSymbol(h.symbol); setHits([]); readYahoo(h.symbol) }}>
                    <span><b>{h.symbol}</b> {h.name}</span><span className="text-ink-3">{h.exchange}</span></button></li>
                ))}
              </ul>
            )}
            <p className="hint">Fetches price, TTM operating income (R&D capitalised when material), effective tax, cash, debt, minorities and the share count. Statements in another currency are converted at spot. Growth, reinvestment and risk inputs stay yours.</p>
          </>
        )}
        {err && <p className="rounded-md bg-bad-soft px-3 py-2 text-[13px] text-bad">{err}</p>}
      </div>

      {res && (
        <div className="mt-5 border-t border-rule pt-4">
          {res.check && (
            <p className={clsx('mb-3 flex items-center gap-2 text-[13px]', res.check.match ? 'text-good' : 'text-warn')}>
              {res.check.match ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
              {res.check.match
                ? `The base case reproduces the sheet's intrinsic value (${res.check.model_value.toFixed(2)} vs ${res.check.sheet_value.toFixed(2)}).`
                : `The base case gives ${res.check.model_value?.toFixed(2)} vs ${res.check.sheet_value.toFixed(2)} in the sheet. Check the fields below.`}
            </p>
          )}
          <div className="max-h-72 overflow-y-auto rounded-md border border-rule">
            <table className="w-full text-[12.5px]">
              <thead className="sticky top-0 bg-paper text-left text-ink-3"><tr><th className="px-3 py-1.5 font-medium">Field</th><th className="px-3 py-1.5 text-right font-medium">Value</th><th className="px-3 py-1.5 font-medium">From</th><th className="px-3 py-1.5 font-medium">Range in notes</th></tr></thead>
              <tbody>
                {Object.entries(res.import.fields).map(([k, f]) => {
                  const sp = specs[k]
                  return (
                    <tr key={k} className="border-t border-rule">
                      <td className="px-3 py-1.5">{sp?.label ?? k}{f.ambiguous && <span className="chip ml-1 bg-warn-soft text-warn">check</span>}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums">{typeof f.value === 'number' ? (sp ? fmtUnit(sp.unit, f.value) : f.value.toLocaleString('en-US', { maximumFractionDigits: 4 })) : f.value}</td>
                      <td className="px-3 py-1.5 text-ink-3">{f.cell}</td>
                      <td className="px-3 py-1.5 text-ink-3">{f.range && sp ? `${fmtUnit(sp.unit, f.range[0])} – ${fmtUnit(sp.unit, f.range[1])}` : ''}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {res.import.messages.length > 0 && (
            <ul className="mt-3 space-y-1 text-[12.5px]">{res.import.messages.map((m, i) => <li key={i} className={m.severity === 'error' ? 'text-bad' : m.severity === 'warning' ? 'text-warn' : 'text-ink-2'}>{m.message}</li>)}</ul>
          )}
          <div className="mt-4 flex flex-wrap justify-end gap-2">
            {src === 'yahoo'
              ? <div className="grid w-full gap-2 sm:grid-cols-2">
                  <button className="btn h-auto flex-col items-start py-2 text-left" onClick={() => { onApply(res.inputs, 'merge', ranges); onOpenChange(false) }}>
                    <span className="font-semibold">Update the financial information only</span>
                    <span className="font-normal text-ink-3">Replaces price, shares, cash, EBIT, debt and tax with Yahoo's figures. Your growth, reinvestment and risk inputs stay as they are.</span></button>
                  <button className="btn h-auto flex-col items-start py-2 text-left" onClick={() => { onApply(res.inputs, 'replace', ranges); onOpenChange(false) }}>
                    <span className="font-semibold">Start from scratch with these figures</span>
                    <span className="font-normal text-ink-3">Clears every input and keeps only what Yahoo provides; you then enter growth, reinvestment and risk yourself.</span></button>
                </div>
              : <button className="btn-primary" onClick={() => { onApply(res.inputs, 'replace', ranges); onOpenChange(false) }}><FileSpreadsheet size={14} /> Use these inputs</button>}
          </div>
        </div>
      )}
    </Modal>
  )
}

function TabPicker({ tabs, tab, setTab }: { tabs: string[]; tab: string; setTab: (t: string) => void }) {
  return (
    <div>
      <span className="label">Company tab</span>
      <div className="mt-1 flex max-h-32 flex-wrap gap-1.5 overflow-y-auto">
        {tabs.map(t => (
          <button key={t} onClick={() => setTab(t)} className={clsx('rounded-md border px-2.5 py-1 text-[12.5px]', t === tab ? 'border-ink bg-ink text-white' : 'border-rule hover:border-rule-strong')}>{t}</button>
        ))}
      </div>
    </div>
  )
}
