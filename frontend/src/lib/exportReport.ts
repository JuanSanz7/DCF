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

/** A4 portrait PDF; tall reports continue on further pages. */
export async function exportPdf(el: HTMLElement, name: string) {
  const [{ jsPDF }, url] = await Promise.all([import('jspdf'), capture(el)])
  const img = new Image()
  img.src = url
  await img.decode()
  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4', compress: true })
  const W = 210, H = 297, M = 8
  const w = W - 2 * M
  const h = (img.height / img.width) * w
  let y = 0
  for (let page = 0; y < h; page++) {
    if (page) pdf.addPage()
    pdf.addImage(url, 'PNG', M, M - y, w, h, undefined, 'FAST')
    y += H - 2 * M
  }
  pdf.save(name + '.pdf')
}
