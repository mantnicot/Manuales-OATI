import { Manual, ManualBlock, OatiBlockType } from '../models/manual.models';
import {
  buildOatiImageNumberMap,
  formatFigureCaption,
  imageScalePercent,
  imageStyleMaxWidth,
  resolveImageData,
} from '../oati/oati-images';
import {
  extractFlowBlocks,
  extractStaticBlocks,
  normalizeManual,
} from '../oati/oati-manual';

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function nl2br(s: string): string {
  return esc(s).replace(/\r\n/g, '\n').replace(/\n/g, '<br/>');
}

/** Rompe cadenas muy largas sin espacios para que el navegador/Word/PDF ajusten líneas. */
function softWrapLongTokens(s: string, maxTok = 40): string {
  if (!s || maxTok < 8) return s;
  const re = new RegExp(`\\S{${maxTok + 1},}`, 'g');
  return s.replace(re, (chunk) => {
    const parts: string[] = [];
    for (let i = 0; i < chunk.length; i += maxTok) {
      parts.push(chunk.slice(i, i + maxTok));
    }
    return parts.join('\u200b');
  });
}

function sectionBodyHtml(raw: string): string {
  const s = raw ?? '';
  if (/<[a-z][\s\S]*>/i.test(s)) {
    return `<div class="body-text body-text--rich">${s}</div>`;
  }
  return `<div class="body-text">${nl2br(softWrapLongTokens(s))}</div>`;
}

function coverBlock(m: Manual): ManualBlock | undefined {
  return extractStaticBlocks(m).find((b) => b.type === 'oati_cover');
}

function crestScaleFromCoverData(d: Record<string, unknown>): number {
  const v = Number(d['crestScalePercent']);
  if (!Number.isFinite(v)) return 100;
  return Math.max(50, Math.min(150, Math.round(v)));
}

function crestInlineStyle(pct: number): string {
  const p = Math.max(50, Math.min(150, Math.round(pct)));
  const mh = (56 * p) / 100;
  const mw = (62 * p) / 100;
  return `max-height:${mh.toFixed(1)}mm;max-width:${mw.toFixed(1)}mm;height:auto;object-fit:contain;`;
}

function oatiHeaderTable(m: Manual): string {
  const d = coverBlock(m)?.data ?? {};
  const logoUd = String(d['logoUdData'] ?? '').trim() || String(d['logoUdUrl'] ?? '').trim();
  const logoOati = String(d['logoOatiData'] ?? '').trim() || String(d['logoOatiUrl'] ?? '').trim();
  const imgUd = logoUd
    ? `<img src="${esc(logoUd)}" alt="Universidad Distrital" class="hdr-logo"/>`
    : `<div class="hdr-ph">Logo<br/>Universidad</div>`;
  const imgOati = logoOati
    ? `<img src="${esc(logoOati)}" alt="OATI" class="hdr-logo"/>`
    : `<div class="hdr-ph">Logo<br/>OATI</div>`;
  return (
    `<table class="oati-head" cellspacing="0" cellpadding="0">` +
    `<tr>` +
    `<td class="hc c1">${imgUd}</td>` +
    `<td class="hc c2">` +
    `<div class="line strong">${esc(String(d['moduleHeaderLine'] ?? ''))}</div>` +
    `<div class="line">${esc(String(d['macroProcess'] ?? ''))}</div>` +
    `<div class="line">${esc(String(d['processLine'] ?? ''))}</div>` +
    `</td>` +
    `<td class="hc c3">` +
    `<div class="line"><span class="lbl">Código:</span> ${esc(String(d['code'] ?? ''))}</div>` +
    `<div class="line"><span class="lbl">Versión:</span> ${esc(String(d['version'] ?? ''))}</div>` +
    `<div class="line"><span class="lbl">Fecha de Aprobación:</span> ${esc(String(d['approvalDate'] ?? ''))}</div>` +
    `</td>` +
    `<td class="hc c4">${imgOati}</td>` +
    `</tr></table>`
  );
}

function coverPage(m: Manual, totalPages: number): string {
  const d = coverBlock(m)?.data ?? {};
  const crestRaw = String(d['crestData'] ?? '').trim() || String(d['crestUrl'] ?? '').trim();
  const cStyle = esc(crestInlineStyle(crestScaleFromCoverData(d)));
  const crestHtml = crestRaw
    ? `<div class="crest-wrap"><img src="${esc(crestRaw)}" alt="Escudo" class="crest" style="${cStyle}"/></div>`
    : `<div class="crest-ph">Escudo institucional</div>`;
  const tp = Math.max(3, totalPages);
  return (
    `<section class="sheet cover-sheet">` +
    oatiHeaderTable(m) +
    `<div class="cover-main">` +
    crestHtml +
    `<div class="inst-line">${esc(String(d['institutionLine'] ?? ''))}</div>` +
    `<div class="central-title">${esc(String(d['centralTitle'] ?? ''))}</div>` +
    `<div class="unit-bottom">${esc(String(d['unitFooterLine'] ?? ''))}</div>` +
    `</div>` +
    `<div class="page-foot"><span>Página 1 de ${tp}</span></div>` +
    `</section>`
  );
}

function tocPage(m: Manual, totalPages: number): string {
  const entries = [
    'INTRODUCCIÓN',
    '1. OBJETIVO',
    '2. ALCANCE',
    '3. RESPONSABLES',
    '4. DEFINICIONES Y SIGLAS',
    '5. DESCRIPCIÓN DE CADA PASO (DETALLADO)',
  ];
  const tp = Math.max(3, totalPages);
  const bodyFirst = 3;
  const bodyLast = tp;
  const lis = entries
    .map((t, i) => {
      const p = i < 5 ? '3' : bodyLast > bodyFirst ? `${bodyFirst}–${bodyLast}` : String(bodyFirst);
      return `<li><span class="toc-t">${esc(t)}</span><span class="toc-p">${p}</span></li>`;
    })
    .join('');
  return (
    `<section class="sheet toc-sheet">` +
    oatiHeaderTable(m) +
    `<h1 class="toc-title">TABLA DE CONTENIDO</h1>` +
    `<ol class="toc-list">${lis}</ol>` +
    `<div class="page-foot"><span>Página 2 de ${tp}</span></div>` +
    `</section>`
  );
}

function sectionByType(
  m: Manual,
  type: OatiBlockType,
  titleHtml: string,
  imgNums: Map<string, number>,
): string {
  const blk = extractStaticBlocks(m).find((b) => b.type === type);
  const text = String(blk?.data['text'] ?? '');
  const img = resolveImageData(blk?.data ?? {});
  const capRaw = String(blk?.data['imageCaption'] ?? '');
  const scale = imageScalePercent(blk?.data ?? {});
  const num = blk ? imgNums.get(blk.id) : undefined;
  const cap = formatFigureCaption(num, capRaw);
  const fig = img
    ? `<figure class="evid"><img src="${esc(img)}" alt="" style="${imageStyleMaxWidth(scale)}"/><figcaption>${esc(
        cap,
      )}</figcaption></figure>`
    : '';
  return (
    `<section class="sec-block">` +
    `<h2 class="sec-h">${titleHtml}</h2>` +
    `${sectionBodyHtml(text)}` +
    `${fig}` +
    `</section>`
  );
}

/** Un bloque por cada paso; las notas siguen al paso anterior (igual que el servidor). */
function splitFlowChunks(flow: ManualBlock[]): ManualBlock[][] {
  if (!flow.length) return [];
  const chunks: ManualBlock[][] = [];
  let cur: ManualBlock[] = [];
  for (const b of flow) {
    if (b.type === 'oati_step') {
      if (cur.length) chunks.push(cur);
      cur = [b];
    } else {
      cur.push(b);
    }
  }
  if (cur.length) chunks.push(cur);
  return chunks;
}

function renderFlowChunk(
  chunk: ManualBlock[],
  imgNums: Map<string, number>,
  stepBase: number,
): { html: string; nextStep: number } {
  let stepNum = stepBase;
  const parts: string[] = [];
  for (const b of chunk) {
    if (b.type === 'oati_step') {
      stepNum += 1;
      const d = b.data;
      const title = esc(String(d['title'] ?? ''));
      const desc = String(d['description'] ?? '');
      const img = resolveImageData(d);
      const capRaw = String(d['imageCaption'] ?? '');
      const scale = imageScalePercent(d);
      const num = imgNums.get(b.id);
      const cap = formatFigureCaption(num, capRaw);
      const fig = img
        ? `<figure class="evid"><img src="${esc(img)}" alt="" style="${imageStyleMaxWidth(scale)}"/><figcaption>${esc(
            cap,
          )}</figcaption></figure>`
        : '';
      parts.push(
        `<div class="oati-step">` +
          `<h3 class="step-title"><span class="step-num">5.${stepNum}</span> ${title}</h3>` +
          `${sectionBodyHtml(desc)}` +
          `${fig}` +
          `</div>`,
      );
    } else if (b.type === 'oati_note') {
      const body = esc(softWrapLongTokens(String(b.data['body'] ?? '')));
      parts.push(
        `<p class="oati-note"><span class="oati-note-tag">Nota:</span> <span class="oati-note-body">${body}</span></p>`,
      );
    }
  }
  return { html: parts.join(''), nextStep: stepNum };
}

function staticSectionsHtml(m: Manual, imgNums: Map<string, number>): string {
  return (
    sectionByType(m, 'oati_intro', 'INTRODUCCIÓN', imgNums) +
    sectionByType(m, 'oati_objective', '1. OBJETIVO', imgNums) +
    sectionByType(m, 'oati_scope', '2. ALCANCE', imgNums) +
    sectionByType(m, 'oati_responsible', '3. RESPONSABLES', imgNums) +
    sectionByType(m, 'oati_definitions', '4. DEFINICIONES Y SIGLAS', imgNums)
  );
}

function bodySheetsHtml(m: Manual, imgNums: Map<string, number>, totalPages: number): string {
  const flow = extractFlowBlocks(normalizeManual(m));
  const chunks = splitFlowChunks(flow);
  const hdr = oatiHeaderTable(m);
  const staticHtml = staticSectionsHtml(m, imgNums);
  const parts: string[] = [];
  let stepBase = 0;

  const pushSheet = (inner: string) => {
    parts.push(`<section class="sheet body-sheet">${hdr}${inner}</section>`);
  };

  if (!chunks.length) {
    const footer =
      `<div class="page-foot wide"><span>Página 3 de ${totalPages}</span>` +
      `<span class="attrib">Desarrollado por Oficina Asesora de Sistemas OATI</span></div>`;
    const emptyFlow =
      `<h2 class="proc-head">5. DESCRIPCIÓN DE CADA PASO (DETALLADO)</h2><div class="proc-wrap"></div>`;
    pushSheet(`${staticHtml}${emptyFlow}${footer}`);
    return parts.join('');
  }

  chunks.forEach((ch, i) => {
    const { html: frag, nextStep } = renderFlowChunk(ch, imgNums, stepBase);
    stepBase = nextStep;
    const pageNum = 3 + i;
    const footer =
      `<div class="page-foot wide"><span>Página ${pageNum} de ${totalPages}</span>` +
      `<span class="attrib">Desarrollado por Oficina Asesora de Sistemas OATI</span></div>`;
    if (i === 0) {
      pushSheet(
        `${staticHtml}<h2 class="proc-head">5. DESCRIPCIÓN DE CADA PASO (DETALLADO)</h2>` +
          `<div class="proc-wrap">${frag}</div>${footer}`,
      );
    } else {
      pushSheet(`<div class="proc-wrap proc-wrap-cont">${frag}</div>${footer}`);
    }
  });
  return parts.join('');
}

export function manualToPreviewHtml(manual: Manual): string {
  const m = normalizeManual(manual);
  const imgNums = buildOatiImageNumberMap(m);
  const nBody = Math.max(1, splitFlowChunks(extractFlowBlocks(m)).length);
  const totalPages = 2 + nBody;

  const css = `
    :root { color-scheme: light; }
    body{margin:0;background:#e5e7eb;font-family:Arial,Helvetica,sans-serif;color:#000;}
    .oati-doc{max-width:820px;margin:0 auto;padding:16px;}
    .sheet{background:#fff;border:1px solid #cbd5e1;box-shadow:0 1px 3px rgba(0,0,0,.08);padding:18mm 14mm;margin:0 auto 20px;position:relative;box-sizing:border-box;}
    .sheet.cover-sheet{display:flex;flex-direction:column;min-height:260mm;}
    .cover-main{flex:1 1 auto;display:flex;flex-direction:column;justify-content:center;align-items:center;padding:8mm 2mm 22mm;min-height:0;text-align:center;}
    .sheet.toc-sheet{min-height:260mm;}
    .sheet.body-sheet{min-height:auto;overflow-x:hidden;overflow-wrap:anywhere;}
    .body-text,.body-text--rich,.oati-note,.oati-note-body,.sec-block,.oati-step,.proc-wrap{overflow-wrap:anywhere;word-wrap:break-word;word-break:break-word;max-width:100%;}
    .body-text--rich *{max-width:100%;overflow-wrap:anywhere;word-break:break-word;}
    .oati-head td{overflow-wrap:anywhere;word-break:break-word;}
    .evid{max-width:100%;}
    .oati-head{width:100%;border-collapse:collapse;border:1px solid #000;table-layout:fixed;margin-bottom:12mm;}
    .oati-head td{border:1px solid #000;vertical-align:middle;padding:6px 8px;font-size:10.5pt;}
    .hc.c1{width:18%;text-align:center;}
    .hc.c2{width:34%;}
    .hc.c3{width:28%;}
    .hc.c4{width:20%;text-align:center;}
    .hdr-logo{max-width:100%;max-height:72px;object-fit:contain;}
    .hdr-ph{color:#6b7280;font-size:9pt;text-align:center;line-height:1.2;}
    .oati-head .line{margin:2px 0 4px;}
    .oati-head .strong{font-weight:700;text-transform:uppercase;}
    .oati-head .lbl{font-weight:600;}
    .crest-wrap,.crest-ph{margin:3mm auto 4mm;text-align:center;}
    .crest{object-fit:contain;}
    .crest-ph{border:1px dashed #9ca3af;color:#6b7280;padding:16px;display:inline-block;font-size:10pt;}
    .inst-line{text-align:center;font-family:'Times New Roman',Times,serif;font-weight:700;font-size:16pt;margin:5mm 0 2mm;width:100%;}
    .central-title{text-align:center;font-weight:700;font-size:14pt;text-transform:uppercase;margin:8mm 0;width:100%;}
    .unit-bottom{text-align:center;font-weight:700;font-size:11pt;text-transform:uppercase;margin-top:10mm;width:100%;}
    .toc-title{text-align:center;font-weight:700;font-size:12pt;margin:6mm 0 8mm;text-transform:uppercase;}
    .toc-list{list-style:none;padding:0;margin:0;}
    .toc-list li{display:flex;justify-content:space-between;align-items:baseline;font-weight:700;text-transform:uppercase;margin:0 0 4mm;font-size:11pt;border-bottom:1px dotted #ccc;}
    .toc-p{color:#111827;min-width:24px;text-align:right;}
    .sec-h{font-size:11pt;font-weight:700;text-transform:uppercase;margin:8mm 0 3mm;}
    .step-title{overflow-wrap:anywhere;word-break:break-word;}
    .body-text{font-size:11pt;line-height:1.22;}
    .evid{margin:4mm 0;text-align:center;}
    .evid img{max-width:100%;border:1px solid #e5e7eb;border-radius:8px;}
    .evid figcaption{font-size:10pt;margin-top:2mm;font-weight:700;}
    .proc-head{font-size:11pt;font-weight:700;text-transform:uppercase;margin:10mm 0 4mm;}
    .proc-wrap-cont{padding-top:10mm;}
    .oati-step{margin:5mm 0 6mm;}
    .step-title{margin:0 0 3mm;font-size:11pt;font-weight:700;text-transform:uppercase;}
    .step-num{margin-right:4px;}
    .oati-note{margin:5mm 0;font-size:11pt;line-height:1.35;}
    .oati-note-tag{font-weight:700;font-style:italic;}
    .oati-note-body{font-style:italic;text-decoration:underline;}
    .page-foot{position:absolute;left:14mm;right:14mm;bottom:10mm;display:flex;justify-content:space-between;font-size:9pt;color:#6b7280;}
    .page-foot.wide{align-items:flex-end;}
    .page-foot .attrib{font-size:7pt;color:#9ca3af;max-width:52%;text-align:right;}
    a{color:#1d4ed8;text-decoration:underline;}
  `.replace(/\s+/g, ' ');

  const body =
    `<div class="oati-doc">` +
    coverPage(m, totalPages) +
    tocPage(m, totalPages) +
    bodySheetsHtml(m, imgNums, totalPages) +
    `</div>`;

  return `<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><style>${css}</style></head><body>${body}</body></html>`;
}
