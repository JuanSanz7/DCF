import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import { C, EChart, baseAxis, tooltipBase } from './EChart'
import type { Heatmap, ParamSpec, Summary, ValuationRow } from '../lib/api'
import { fmtNum, fmtPct, fmtUnit, isPct } from '../lib/format'

const num = (v: number, d = 2) => fmtNum(v, d)

const sigmaLegend = [
  { name: '±1σ', icon: 'rect', itemStyle: { color: 'rgba(22,163,74,0.35)' } },
  { name: '±2σ', icon: 'rect', itemStyle: { color: 'rgba(234,170,0,0.4)' } },
  { name: '±3σ', icon: 'rect', itemStyle: { color: 'rgba(220,38,38,0.3)' } },
]
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const sigmaBand = (name: string, color: string, data: [number, number][]): any =>
  ({ type: 'line' as const, name, data: [], markArea: { silent: true, itemStyle: { color }, data: data.map(([a, b]) => [{ xAxis: a }, { xAxis: b }]) } })

/** Distribution of intrinsic value with the ±1/2/3σ ranges, the mean and the market price. */
export function ValueField({ s, currency, height = 340 }: { s: Summary; currency: string; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const h = s.histogram!
    const price = s.price
    const m = s.mean!, sd = s.sd!
    const lo = h.edges[0], hi = h.edges[h.edges.length - 1]
    const clip = (x: number) => Math.max(lo, Math.min(hi, x))
    const bars = h.counts.map((c, i) => ({ value: [h.edges[i], h.edges[i + 1], c / h.total / (h.edges[i + 1] - h.edges[i])] }))
    const ymax = Math.max(...bars.map(b => b.value[2]))
    return {
      grid: { left: 8, right: 16, top: 34, bottom: 30, containLabel: true },
      legend: { top: 0, right: 0, itemWidth: 14, itemHeight: 8, textStyle: { color: C.ink2, fontSize: 11 },
        data: [...sigmaLegend, { name: 'Mean', itemStyle: { color: C.mean } }, { name: 'Current price', itemStyle: { color: C.market } }] },
      tooltip: { ...tooltipBase, trigger: 'item', formatter: (q: unknown) => {
        const d = (q as { value?: number[] }).value
        if (!d || d.length < 3) return ''
        return `${num(d[0])} – ${num(d[1])} ${currency}<br/><b>${fmtPct(d[2] * (d[1] - d[0]), 1)}</b> of paths`
      } },
      xAxis: { ...baseAxis, type: 'value', min: lo, max: hi, name: `Intrinsic value per share (${currency})`, nameLocation: 'middle', nameGap: 26, splitLine: { show: false },
        axisLabel: { ...baseAxis.axisLabel, showMinLabel: false, showMaxLabel: false, formatter: (v: number) => num(v, 0) } },
      yAxis: { ...baseAxis, type: 'value', name: 'Density', max: ymax * 1.12, axisLabel: { ...baseAxis.axisLabel, formatter: (v: number) => v.toPrecision(2) } },
      series: [
        sigmaBand('±3σ', C.s3, [[clip(m - 3 * sd), clip(m - 2 * sd)], [clip(m + 2 * sd), clip(m + 3 * sd)]]),
        sigmaBand('±2σ', C.s2, [[clip(m - 2 * sd), clip(m - sd)], [clip(m + sd), clip(m + 2 * sd)]]),
        sigmaBand('±1σ', C.s1, [[clip(m - sd), clip(m + sd)]]),
        {
          type: 'custom', name: 'paths', z: 3,
          renderItem: (_p, api) => {
            const a = api.coord([api.value(0), api.value(2)]), b = api.coord([api.value(1), 0])
            return { type: 'rect', shape: { x: a[0] + 0.5, y: a[1], width: Math.max(b[0] - a[0] - 1, 1), height: b[1] - a[1] },
              style: { fill: C.bar, stroke: C.barEdge, lineWidth: 0.6 } }
          },
          encode: { x: [0, 1], y: 2 }, data: bars,
        },
        { type: 'line', name: 'Mean', data: [], itemStyle: { color: C.mean }, z: 4, markLine: { symbol: 'none', silent: true, data: [
          { xAxis: m, lineStyle: { color: C.mean, width: 1.5, type: 'dashed' }, label: { show: false } }] } },
        { type: 'line', name: 'Current price', data: [], itemStyle: { color: C.market }, z: 4, markLine: { symbol: 'none', silent: true, data: [
          { xAxis: price, lineStyle: { color: C.market, width: 2, type: 'solid' }, label: { formatter: `${num(price)}`, color: C.market, fontWeight: 600, position: 'end' } }] } },
      ],
    }
  }, [s, currency])
  return <EChart option={option} height={height} />
}

export function CdfChart({ s, currency, height = 260 }: { s: Summary; currency: string; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const e = s.ecdf!
    const pts = e.x.map((x, i) => [x, e.q[i]])
    const pUnder = 1 - (s.prob_above_price ?? 0)
    return {
      grid: { left: 8, right: 20, top: 16, bottom: 28, containLabel: true },
      tooltip: { ...tooltipBase, trigger: 'axis', formatter: (q: unknown) => {
        const d = (q as { value: number[] }[])[0].value
        return `${fmtPct(d[1], 0)} of paths below <b>${num(d[0])} ${currency}</b>`
      } },
      xAxis: { ...baseAxis, type: 'value', scale: true, name: currency, nameLocation: 'middle', nameGap: 26 },
      yAxis: { ...baseAxis, type: 'value', max: 1, axisLabel: { ...baseAxis.axisLabel, formatter: (v: number) => fmtPct(v, 0) } },
      series: [{
        type: 'line', data: pts, showSymbol: false, lineStyle: { color: C.value, width: 2 }, areaStyle: { color: C.valueSoft },
        markLine: { symbol: 'none', silent: true, data: [
          { xAxis: s.price, lineStyle: { color: C.market, width: 2 }, label: { formatter: `Price: ${fmtPct(pUnder, 0)} of paths below`, color: C.market, position: 'insideEndTop' } },
        ] },
      }],
    }
  }, [s, currency])
  return <EChart option={option} height={height} />
}

export function FanChart({ s, currency, height = 300 }: { s: Summary; currency: string; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const f = s.fan!
    const yrs = f.year.map(String)
    const mean = f.mean ?? f.p50, sd = f.sd ?? f.p50.map(() => 0)
    const band = (k0: number, k1: number, name: string, color: string) => {
      const lower = mean.map((m, i) => m - k1 * sd[i]), upper = mean.map((m, i) => m - k0 * sd[i])
      const lower2 = mean.map((m, i) => m + k0 * sd[i]), upper2 = mean.map((m, i) => m + k1 * sd[i])
      return [
        { type: 'line' as const, data: lower, stack: name + 'a', lineStyle: { opacity: 0 }, showSymbol: false, silent: true },
        { type: 'line' as const, name, data: upper.map((u, i) => u - lower[i]), stack: name + 'a', lineStyle: { opacity: 0 }, showSymbol: false, areaStyle: { color }, itemStyle: { color }, silent: true },
        { type: 'line' as const, data: lower2, stack: name + 'b', lineStyle: { opacity: 0 }, showSymbol: false, silent: true },
        { type: 'line' as const, data: upper2.map((u, i) => u - lower2[i]), stack: name + 'b', lineStyle: { opacity: 0 }, showSymbol: false, areaStyle: { color }, silent: true },
      ]
    }
    return {
      grid: { left: 8, right: 16, top: 30, bottom: 26, containLabel: true },
      legend: { top: 0, right: 0, textStyle: { color: C.ink2, fontSize: 11 }, itemWidth: 14, itemHeight: 8,
        data: [...sigmaLegend, { name: 'Average FCFF', itemStyle: { color: C.value } }, { name: 'Base case', itemStyle: { color: C.ink } }] },
      tooltip: { ...tooltipBase, trigger: 'axis', formatter: (q: unknown) => {
        const i = (q as { dataIndex: number }[])[0].dataIndex
        return `Year ${f.year[i]}<br/>Average <b>${num(mean[i], 0)}m</b> ± ${num(sd[i], 0)}m (1σ)<br/>Base case ${num(f.base[i], 0)}m ${currency}`
      } },
      xAxis: { ...baseAxis, type: 'category', data: yrs, name: 'Year', nameLocation: 'middle', nameGap: 22, boundaryGap: false },
      yAxis: { ...baseAxis, type: 'value', name: `FCFF (m ${currency})`, axisLabel: { ...baseAxis.axisLabel, formatter: (v: number) => num(v, 0) } },
      series: [
        ...band(2, 3, '±3σ', 'rgba(220,38,38,0.10)'),
        ...band(1, 2, '±2σ', 'rgba(234,170,0,0.16)'),
        ...band(0, 1, '±1σ', 'rgba(22,163,74,0.16)').slice(0, 2).map((x, i) => (i === 0 ? { ...x, data: mean.map((m, j) => m - sd[j]) } : { ...x, data: sd.map(v => 2 * v) })),
        { type: 'line', name: 'Average FCFF', data: mean, symbol: 'circle', symbolSize: 6, lineStyle: { color: C.value, width: 2 }, itemStyle: { color: C.value } },
        { type: 'line', name: 'Base case', data: f.base, showSymbol: false, lineStyle: { color: C.ink, width: 1.25, type: 'dashed' }, itemStyle: { color: C.ink } },
      ],
    }
  }, [s, currency])
  return <EChart option={option} height={height} />
}

export function Tornado({ s, specs, currency, height }: { s: Summary; specs: Record<string, ParamSpec>; currency: string; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const t = [...(s.tornado ?? [])].reverse()
    const base = s.base.value_per_share ?? 0
    const lbl = (r: (typeof t)[number]) => {
      const sp = specs[r.key]
      return `${r.label}  ${fmtUnit(sp.unit, r.input_low)} → ${fmtUnit(sp.unit, r.input_high)}`
    }
    return {
      grid: { left: 8, right: 24, top: 18, bottom: 26, containLabel: true },
      tooltip: { ...tooltipBase, trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (q: unknown) => {
        const i = (q as { dataIndex: number }[])[0].dataIndex
        const r = t[i]
        const sp = specs[r.key]
        return `<b>${r.label}</b><br/>P10 ${fmtUnit(sp.unit, r.input_low)} → ${num(r.value_low!)} ${currency}<br/>P90 ${fmtUnit(sp.unit, r.input_high)} → ${num(r.value_high!)} ${currency}`
      } },
      xAxis: { ...baseAxis, type: 'value', scale: true, name: `Value per share (${currency}), others at base`, nameLocation: 'middle', nameGap: 24,
        min: (e: { min: number }) => Math.floor(Math.min(e.min, s.price * 0.97)), max: (e: { max: number }) => Math.ceil(Math.max(e.max, s.price * 1.03)) },
      yAxis: { ...baseAxis, type: 'category', data: t.map(lbl), axisLabel: { ...baseAxis.axisLabel, color: C.ink2, fontSize: 11 } },
      series: [
        { type: 'bar', stack: 'a', silent: true, itemStyle: { color: 'transparent' }, data: t.map(r => Math.min(r.value_low ?? base, r.value_high ?? base)) },
        { type: 'bar', stack: 'a', barWidth: 14, data: t.map(r => ({
          value: Math.abs((r.value_high ?? base) - (r.value_low ?? base)),
          itemStyle: { color: (r.value_high ?? 0) >= (r.value_low ?? 0) ? '#1f77b4' : '#6b7a99', borderRadius: 2 },
        })) },
        { type: 'line', data: [], markLine: { symbol: 'none', silent: true, data: [
          { xAxis: base, lineStyle: { color: C.ink, type: 'dashed' }, label: { formatter: 'Base', color: C.ink3, fontSize: 10, position: 'insideEndTop' } },
          { xAxis: s.price, lineStyle: { color: C.market, width: 2 }, label: { formatter: 'Price', color: C.market, fontSize: 10, position: 'insideEndTop' } },
        ] } },
      ],
    }
  }, [s, specs, currency])
  return <EChart option={option} height={height ?? Math.max(160, 44 * (s.tornado?.length ?? 1) + 50)} />
}

export function HeatmapChart({ h, specs, mode, price, currency, height = 360 }: {
  h: Heatmap; specs: Record<string, ParamSpec>; mode: 'value' | 'prob'; price: number; currency: string; height?: number
}) {
  const option = useMemo<EChartsOption>(() => {
    const sx = specs[h.x_key], sy = specs[h.y_key]
    const data: [number, number, number | null, number][] = []
    h.median.forEach((row, j) => row.forEach((m, i) => {
      const v = mode === 'value' ? m : h.prob_above_price?.[j]?.[i] ?? null
      data.push([i, j, v == null ? null : v, h.count[j][i]])
    }))
    const vals = data.map(d => d[2]).filter((v): v is number => v != null)
    const lab = (s: ParamSpec | undefined, v: number) => (s ? fmtUnit(s.unit, v) : num(v))
    return {
      grid: { left: 8, right: 70, top: 10, bottom: 34, containLabel: true },
      tooltip: { ...tooltipBase, formatter: (q: unknown) => {
        const d = (q as { value: number[] }).value
        const xs = `${lab(sx, h.x_edges[d[0]])} – ${lab(sx, h.x_edges[d[0] + 1])}`
        const ys = `${lab(sy, h.y_edges[d[1]])} – ${lab(sy, h.y_edges[d[1] + 1])}`
        const v = mode === 'value' ? `median value <b>${num(d[2])} ${currency}</b>` : `<b>${fmtPct(d[2], 0)}</b> of paths above price`
        return `${sx?.label ?? h.x_key}: ${xs}<br/>${sy?.label ?? h.y_key}: ${ys}<br/>${v}<br/><span style="color:${C.ink3}">${d[3]} paths</span>`
      } },
      xAxis: { ...baseAxis, type: 'category', data: h.x.map(v => lab(sx, v)), name: sx?.label ?? h.x_key, nameLocation: 'middle', nameGap: 26, splitArea: { show: false } },
      yAxis: { ...baseAxis, type: 'category', data: h.y.map(v => lab(sy, v)), name: sy?.label ?? h.y_key, nameLocation: 'middle', nameGap: 56 },
      visualMap: mode === 'value'
        ? { type: 'piecewise', dimension: 2, right: 0, top: 'middle', orient: 'vertical', textStyle: { color: C.ink2, fontSize: 11 },
            pieces: [
              { min: price * 1.3, label: `≥ 1.3× price`, color: '#0b5f67' },
              { min: price, max: price * 1.3, label: 'price to 1.3×', color: '#5fb3b8' },
              { min: price * 0.8, max: price, label: '0.8× to price', color: '#eab8cf' },
              { max: price * 0.8, label: '< 0.8× price', color: '#b4236a' },
            ] }
        : { type: 'continuous', dimension: 2, min: 0, max: 1, right: 0, top: 'middle', calculable: false, itemHeight: 140, text: ['100%', '0%'], textStyle: { color: C.ink2, fontSize: 11 }, inRange: { color: ['#d27fa4', '#f4eef1', '#0e7c86'] } },
      series: [{ type: 'heatmap', data, itemStyle: { borderColor: '#fff', borderWidth: 1 }, label: { show: true, fontSize: 10, color: C.ink,
        formatter: (q: unknown) => { const v = (q as { value: number[] }).value[2]; return v == null ? '' : mode === 'value' ? num(v, 0) : fmtPct(v, 0) } } }],
      ...(vals.length ? {} : { title: { text: 'No data' } }),
    } as EChartsOption
  }, [h, specs, mode, price, currency])
  return <EChart option={option} height={height} />
}

export function ScatterExplorer({ s, xKey, spec, currency, height = 320 }: { s: Summary; xKey: string; spec: ParamSpec; currency: string; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const xs = s.sample?.[xKey] ?? [], vs = s.sample?.value ?? []
    const f = isPct(spec.unit) ? 100 : 1
    const pts = xs.map((x, i) => [x * f, vs[i]])
    return {
      grid: { left: 8, right: 16, top: 16, bottom: 30, containLabel: true },
      tooltip: { ...tooltipBase, trigger: 'item', formatter: (q: unknown) => { const d = (q as { value: number[] }).value; return `${spec.label}: ${fmtUnit(spec.unit, d[0] / f)}<br/>Value: <b>${num(d[1])} ${currency}</b>` } },
      xAxis: { ...baseAxis, type: 'value', scale: true, name: spec.label + (isPct(spec.unit) ? ' (%)' : ''), nameLocation: 'middle', nameGap: 26 },
      yAxis: { ...baseAxis, type: 'value', scale: true, name: currency },
      series: [{ type: 'scatter', data: pts, symbolSize: 4, itemStyle: { color: C.value, opacity: 0.35 }, large: true,
        markLine: { symbol: 'none', silent: true, data: [{ yAxis: s.price, lineStyle: { color: C.market, width: 2 }, label: { formatter: 'Price', color: C.market } }] } }],
    }
  }, [s, xKey, spec, currency])
  return <EChart option={option} height={height} />
}

export function ConvergenceChart({ s, height = 220 }: { s: Summary; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const c = s.convergence!
    return {
      grid: { left: 8, right: 16, top: 24, bottom: 28, containLabel: true },
      legend: { top: 0, right: 0, textStyle: { color: C.ink2, fontSize: 11 } },
      tooltip: { ...tooltipBase, trigger: 'axis' },
      xAxis: { ...baseAxis, type: 'log', name: 'Paths', nameLocation: 'middle', nameGap: 24 },
      yAxis: { ...baseAxis, type: 'value', scale: true },
      series: [
        { type: 'line', name: '95% band (mean)', data: c.n.map((n, i) => [n, c.lo[i]]), showSymbol: false, lineStyle: { color: C.ink3, type: 'dotted' } },
        { type: 'line', name: ' ', data: c.n.map((n, i) => [n, c.hi[i]]), showSymbol: false, lineStyle: { color: C.ink3, type: 'dotted' } },
        { type: 'line', name: 'Mean', data: c.n.map((n, i) => [n, c.mean[i]]), showSymbol: false, lineStyle: { color: C.value, width: 2 } },
        { type: 'line', name: 'Median', data: c.n.map((n, i) => [n, c.median[i]]), showSymbol: false, lineStyle: { color: C.ink, width: 1.5 } },
      ],
    }
  }, [s])
  return <EChart option={option} height={height} />
}

export function DistPreview({ density, unit, base, height = 120 }: { density: { x: number[]; y: number[]; discrete: boolean }; unit: ParamSpec['unit']; base: number | null; height?: number }) {
  const option = useMemo<EChartsOption>(() => {
    const f = isPct(unit) ? 100 : 1
    const pts = density.x.map((x, i) => [x * f, density.y[i]])
    return {
      grid: { left: 4, right: 4, top: 8, bottom: 20, containLabel: true },
      xAxis: { ...baseAxis, type: 'value', scale: true, axisLabel: { ...baseAxis.axisLabel, formatter: (v: number) => fmtNum(v, isPct(unit) ? 1 : 2) + (isPct(unit) ? '%' : '') }, splitLine: { show: false } },
      yAxis: { type: 'value', show: false },
      series: [density.discrete
        ? { type: 'bar', data: pts, barWidth: 6, itemStyle: { color: C.value } }
        : { type: 'line', data: pts, showSymbol: false, smooth: true, lineStyle: { color: C.value, width: 1.5 }, areaStyle: { color: C.valueSoft },
            markLine: base == null ? undefined : { symbol: 'none', silent: true, data: [{ xAxis: base * f, lineStyle: { color: C.ink, type: 'dashed' }, label: { formatter: 'base', fontSize: 10, color: C.ink3, position: 'insideEndTop' } }] } }],
    }
  }, [density, unit, base])
  return <EChart option={option} height={height} />
}

/** History of a company: each valuation as a P10–P90 whisker with its median, over the price path. */
export function HistoryChart({ runs, prices, currency, height = 360, onSelect }: {
  runs: ValuationRow[]; prices: { dates: string[]; close: number[] } | null; currency: string; height?: number; onSelect?: (id: string) => void
}) {
  const option = useMemo<EChartsOption>(() => {
    const whiskers = runs.filter(r => r.median != null).map(r => ({ value: [r.created_at, r.p10 ?? r.median, r.p90 ?? r.median, r.median, r.price], id: r.id }))
    const times = runs.map(r => +new Date(r.created_at))
    const pad = Math.max((Math.max(...times) - Math.min(...times)) * 0.06, 20 * 864e5)
    const xmin = Math.min(...times, ...(prices?.dates.length ? [+new Date(prices.dates[0])] : [])) - pad
    const xmax = Math.max(...times, ...(prices?.dates.length ? [+new Date(prices.dates[prices.dates.length - 1])] : [])) + pad
    return {
      grid: { left: 8, right: 20, top: 30, bottom: 30, containLabel: true },
      legend: { top: 0, right: 0, textStyle: { color: C.ink2, fontSize: 11 }, itemWidth: 14, itemHeight: 8,
        data: [{ name: 'Intrinsic value P10–P90 and median', itemStyle: { color: C.value } }, { name: 'Price on valuation day', itemStyle: { color: C.market } }, ...(prices ? [{ name: 'Market price', itemStyle: { color: C.market } }] : [])] },
      tooltip: { ...tooltipBase, trigger: 'item', formatter: (q: unknown) => {
        const p = q as { seriesName: string; value: (string | number)[] }
        if (p.seriesName !== 'Intrinsic value P10–P90 and median') return `${new Date(p.value[0] as string).toLocaleDateString('en-GB')}<br/>Price <b>${num(p.value[1] as number)} ${currency}</b>`
        const v = p.value
        return `${new Date(v[0] as string).toLocaleDateString('en-GB')}<br/>Median <b>${num(v[3] as number)}</b> · P10–P90 ${num(v[1] as number)} – ${num(v[2] as number)} ${currency}<br/>Price then ${num(v[4] as number)}<br/><span style="color:${C.ink3}">Click to open</span>`
      } },
      xAxis: { ...baseAxis, type: 'time', min: xmin, max: xmax },
      yAxis: { ...baseAxis, type: 'value', scale: true, name: currency },
      series: [
        ...(prices ? [{ type: 'line' as const, name: 'Market price', data: prices.dates.map((d, i) => [d, prices.close[i]]), showSymbol: false, lineStyle: { color: C.market, width: 1.25, opacity: 0.8 }, itemStyle: { color: C.market }, z: 1 }] : []),
        {
          type: 'custom', name: 'Intrinsic value P10–P90 and median', z: 3, data: whiskers, itemStyle: { color: C.value },
          renderItem: (_p, api) => {
            const lo = api.coord([api.value(0), api.value(1)]), hi = api.coord([api.value(0), api.value(2)])
            const md = api.coord([api.value(0), api.value(3)])
            return { type: 'group', children: [
              { type: 'rect', shape: { x: lo[0] - 6, y: hi[1], width: 12, height: lo[1] - hi[1], r: 3 }, style: { fill: 'rgba(14,124,134,0.22)', stroke: C.value, lineWidth: 1 } },
              { type: 'circle', shape: { cx: md[0], cy: md[1], r: 4.5 }, style: { fill: C.value, stroke: '#fff', lineWidth: 1.5 } },
            ] }
          },
          encode: { x: 0, y: [1, 2, 3] },
        },
        { type: 'scatter', name: 'Price on valuation day', z: 4, symbol: 'rect', symbolSize: [18, 2.5], itemStyle: { color: C.market },
          data: runs.filter(r => r.price != null).map(r => [r.created_at, r.price]) },
      ],
    }
  }, [runs, prices, currency])
  return <EChart option={option} height={height} onClick={onSelect ? (p) => { const d = p.data as { id?: string } | undefined; if (d?.id) onSelect(d.id) } : undefined} />
}
