import * as Dialog from '@radix-ui/react-dialog'
import * as Tooltip from '@radix-ui/react-tooltip'
import { clsx } from 'clsx'
import { AlertTriangle, CircleAlert, Info, X } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import type { Issue } from '../lib/api'

export function Tip({ content, children, side = 'top' }: { content: ReactNode; children: ReactNode; side?: 'top' | 'right' | 'bottom' | 'left' }) {
  return (
    <Tooltip.Root delayDuration={250}>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content side={side} sideOffset={6} collisionPadding={12}
          className="z-50 max-w-sm rounded-md border border-rule bg-panel px-3 py-2 text-[12px] leading-relaxed text-ink-2 shadow-[0_8px_30px_rgba(20,33,61,.12)]">
          {content}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  )
}

export function Modal({ open, onOpenChange, title, description, children, wide }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; description?: string; children: ReactNode; wide?: boolean
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/25 backdrop-blur-[1px]" />
        <Dialog.Content className={clsx('fixed left-1/2 top-[5vh] z-50 max-h-[90vh] w-[calc(100vw-2rem)] -translate-x-1/2 overflow-y-auto rounded-lg border border-rule bg-panel shadow-[0_24px_80px_rgba(20,33,61,.22)]', wide ? 'max-w-5xl' : 'max-w-2xl')}>
          <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-rule bg-panel px-5 py-3.5">
            <div>
              <Dialog.Title className="font-cond text-[17px] font-semibold">{title}</Dialog.Title>
              {description && <Dialog.Description className="hint mt-0.5">{description}</Dialog.Description>}
            </div>
            <Dialog.Close className="btn-ghost" aria-label="Close"><X size={16} /></Dialog.Close>
          </div>
          <div className="px-5 py-4">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

const sevIcon = { error: CircleAlert, warning: AlertTriangle, info: Info }
const sevCls = { error: 'text-bad bg-bad-soft', warning: 'text-warn bg-warn-soft', info: 'text-ink-2 bg-paper' }

export function IssueList({ issues, onPick, compact }: { issues: Issue[]; onPick?: (key: string) => void; compact?: boolean }) {
  if (!issues.length) return null
  const order = { error: 0, warning: 1, info: 2 }
  const sorted = [...issues].sort((a, b) => order[a.severity] - order[b.severity])
  return (
    <ul className="space-y-1.5">
      {sorted.map((i, k) => {
        const Icon = sevIcon[i.severity]
        return (
          <li key={k} className={clsx('flex items-start gap-2 rounded-md px-2.5 py-1.5 text-[12.5px] leading-snug', sevCls[i.severity])}>
            <Icon size={14} className="mt-0.5 shrink-0" />
            <span className="text-ink">
              {i.message}
              {i.param && onPick && !compact && (
                <button className="ml-1 underline decoration-dotted underline-offset-2 hover:text-value" onClick={() => onPick(i.param!)}>Go to input</button>
              )}
            </span>
          </li>
        )
      })}
    </ul>
  )
}

/** Numeric input in display units that accepts "4,65" or "4.65" and commits on blur/Enter. */
export function NumberField({ value, onCommit, suffix, placeholder, className, ariaLabel, invalid }: {
  value: number | null; onCommit: (v: number | null) => void; suffix?: string; placeholder?: string; className?: string; ariaLabel?: string; invalid?: boolean
}) {
  const show = (v: number | null) => (v == null || !Number.isFinite(v) ? '' : String(+v.toPrecision(7)))
  const [text, setText] = useState(show(value))
  useEffect(() => { setText(show(value)) }, [value])
  const commit = () => {
    const t = text.trim().replace(/\s/g, '')
    if (t === '') { if (value != null) onCommit(null); return }
    let s = t
    if (s.includes(',') && s.includes('.')) s = s.lastIndexOf(',') > s.lastIndexOf('.') ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '')
    else if (s.includes(',')) s = s.replace(',', '.')
    const v = Number(s.replace(/[^0-9eE+.-]/g, ''))
    if (Number.isFinite(v)) { if (v !== value) onCommit(v) } else setText(show(value))
  }
  return (
    <div className={clsx('relative', className)}>
      <input inputMode="decimal" aria-label={ariaLabel} value={text} placeholder={placeholder}
        onChange={e => setText(e.target.value)} onBlur={commit} onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
        className={clsx('field text-right tabular-nums', suffix && (suffix.length > 2 ? 'pr-10' : 'pr-7'), invalid && 'border-bad focus:border-bad')} />
      {suffix && <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-ink-3">{suffix}</span>}
    </div>
  )
}

export function Segmented<T extends string>({ value, options, onChange, size = 'sm' }: {
  value: T; options: { value: T; label: string; hint?: string }[]; onChange: (v: T) => void; size?: 'sm' | 'xs'
}) {
  return (
    <div className="inline-flex rounded-md border border-rule bg-paper p-0.5" role="radiogroup">
      {options.map(o => {
        const b = (
          <button key={o.value} role="radio" aria-checked={value === o.value} onClick={() => onChange(o.value)}
            className={clsx('rounded-[5px] px-2.5 font-medium transition-colors', size === 'sm' ? 'h-7 text-[12px]' : 'h-6 text-[11px]',
              value === o.value ? 'bg-panel text-ink shadow-[0_1px_2px_rgba(20,33,61,.12)]' : 'text-ink-3 hover:text-ink')}>
            {o.label}
          </button>
        )
        return o.hint ? <Tip key={o.value} content={o.hint}>{b}</Tip> : b
      })}
    </div>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <span className={clsx('inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-r-transparent', className)} aria-hidden />
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-lg border border-dashed border-rule-strong px-6 py-10">
      <h3 className="text-[17px] font-semibold">{title}</h3>
      {children && <div className="max-w-prose text-[13px] text-ink-2">{children}</div>}
      {action}
    </div>
  )
}

/** P10–P90 range drawn against price on a shared scale (portfolio + runs tables). */
export function RangeBar({ p10, median, p90, price, lo, hi, width = 180 }: {
  p10: number | null; median: number | null; p90: number | null; price: number | null; lo: number; hi: number; width?: number
}) {
  if (p10 == null || p90 == null || median == null) return <span className="hint">–</span>
  const x = (v: number) => 4 + ((v - lo) / Math.max(hi - lo, 1e-9)) * (width - 8)
  return (
    <svg width={width} height={20} role="img" aria-label={`P10 ${p10.toFixed(0)}, median ${median.toFixed(0)}, P90 ${p90.toFixed(0)}, price ${price?.toFixed(0)}`}>
      <line x1={4} x2={width - 4} y1={10} y2={10} stroke="#eceee8" strokeWidth={2} />
      <rect x={x(p10)} y={5} width={Math.max(x(p90) - x(p10), 2)} height={10} rx={3} fill="rgba(0,119,182,0.18)" stroke="#0077b6" strokeWidth={1} />
      <circle cx={x(median)} cy={10} r={3.5} fill="#0077b6" stroke="#fff" strokeWidth={1.25} />
      {price != null && <line x1={x(price)} x2={x(price)} y1={1} y2={19} stroke="#7b2d8e" strokeWidth={2} />}
    </svg>
  )
}
