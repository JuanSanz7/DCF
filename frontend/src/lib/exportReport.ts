import { toPng } from 'html-to-image'

async function capture(el: HTMLElement): Promise<string> {
  return toPng(el, { pixelRatio: 2, backgroundColor: '#ffffff', cacheBust: true,
    filter: n => !(n instanceof HTMLElement && n.dataset.noExport === 'true') })
}

function download(href: string, name: string) {
  const a = document.createElement('a')
  a.href = href; a.download = name; a.click()
}

export async function exportPng(el: HTMLElement, name: string) {
  download(await capture(el), name + '.png')
}

/** One A4 page: the report is scaled to fit (landscape when it is wider than tall). */
export async function exportPdf(el: HTMLElement, name: string) {
  const [{ jsPDF }, url] = await Promise.all([import('jspdf'), capture(el)])
  const img = new Image()
  img.src = url
  await img.decode()
  const landscape = img.width > img.height
  const pdf = new jsPDF({ orientation: landscape ? 'landscape' : 'portrait', unit: 'mm', format: 'a4', compress: true })
  const W = landscape ? 297 : 210, H = landscape ? 210 : 297, M = 7
  const k = Math.min((W - 2 * M) / img.width, (H - 2 * M) / img.height)
  const w = img.width * k, h = img.height * k
  pdf.addImage(url, 'PNG', (W - w) / 2, M, w, h, undefined, 'FAST')
  pdf.save(name + '.pdf')
}
