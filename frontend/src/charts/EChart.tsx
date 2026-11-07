import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

export const C = {
  ink: '#14213d', ink2: '#44506a', ink3: '#7a8499', rule: '#dde1d8', grid: '#eceee8',
  value: '#0e7c86', valueSoft: 'rgba(14,124,134,0.16)', valueMid: 'rgba(14,124,134,0.35)',
  market: '#b4236a', marketSoft: 'rgba(180,35,106,0.12)', bad: '#b42318', warn: '#a85d00',
}
export const FONT = '"IBM Plex Sans", system-ui, sans-serif'

export const baseAxis = {
  axisLine: { lineStyle: { color: C.rule } }, axisTick: { show: false },
  axisLabel: { color: C.ink3, fontFamily: FONT, fontSize: 11 },
  splitLine: { lineStyle: { color: C.grid } },
  nameTextStyle: { color: C.ink3, fontFamily: FONT, fontSize: 11 },
}
export const tooltipBase = {
  backgroundColor: '#fff', borderColor: C.rule, borderWidth: 1, padding: [8, 10],
  textStyle: { color: C.ink, fontFamily: FONT, fontSize: 12 },
  extraCssText: 'box-shadow: 0 6px 24px rgba(20,33,61,.10); border-radius: 6px;',
}

export function EChart({ option, height = 300, className, onClick }: {
  option: echarts.EChartsOption; height?: number | string; className?: string
  onClick?: (p: echarts.ECElementEvent) => void
}) {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  useEffect(() => {
    if (!el.current) return
    const c = echarts.init(el.current, undefined, { renderer: 'canvas' })
    chart.current = c
    const ro = new ResizeObserver(() => c.resize())
    ro.observe(el.current)
    return () => { ro.disconnect(); c.dispose(); chart.current = null }
  }, [])
  useEffect(() => {
    chart.current?.setOption({ textStyle: { fontFamily: FONT }, animationDuration: 350, ...option }, true)
  }, [option])
  useEffect(() => {
    const c = chart.current
    if (!c || !onClick) return
    c.on('click', onClick)
    return () => { c.off('click', onClick) }
  }, [onClick])
  return <div ref={el} className={className} style={{ height, width: '100%' }} />
}
