import { Manual, ManualBlock, OatiBlockType } from '../models/manual.models';
import { extractFlowBlocks, extractStaticBlocks, normalizeManual } from './oati-manual';

const STATIC_IMAGE_ORDER: OatiBlockType[] = [
  'oati_intro',
  'oati_objective',
  'oati_scope',
  'oati_responsible',
  'oati_definitions',
];

/** URL remota o data URL (subida desde archivo). */
export function resolveImageData(data: Record<string, unknown>): string {
  const embedded = String(data['imageData'] ?? '').trim();
  if (embedded) return embedded;
  return String(data['imageSrc'] ?? '').trim();
}

export function imageScalePercent(data: Record<string, unknown>): number {
  const v = Number(data['imageScalePercent']);
  if (!Number.isFinite(v)) return 100;
  return Math.min(100, Math.max(25, Math.round(v)));
}

/** Orden documental: módulos 2–6 con imagen, luego cada paso con imagen. */
export function buildOatiImageNumberMap(manual: Manual): Map<string, number> {
  const m = normalizeManual(manual);
  const smap = new Map<OatiBlockType, ManualBlock>();
  for (const b of extractStaticBlocks(m)) {
    if (STATIC_IMAGE_ORDER.includes(b.type as OatiBlockType)) {
      smap.set(b.type as OatiBlockType, b);
    }
  }
  const ids: string[] = [];
  for (const t of STATIC_IMAGE_ORDER) {
    const b = smap.get(t);
    if (b && resolveImageData(b.data)) ids.push(b.id);
  }
  for (const b of extractFlowBlocks(m)) {
    if (b.type === 'oati_step' && resolveImageData(b.data)) ids.push(b.id);
  }
  const map = new Map<string, number>();
  ids.forEach((id, i) => map.set(id, i + 1));
  return map;
}

export function formatFigureCaption(num: number | undefined, userText: string): string {
  const prefix = num != null ? `Imagen ${num}.` : '';
  const t = (userText ?? '').trim();
  if (!prefix) return t;
  if (!t) return prefix;
  return `${prefix} ${t}`;
}

export function imageStyleMaxWidth(scalePct: number): string {
  const p = Math.min(100, Math.max(25, Math.round(Number(scalePct) || 100)));
  return `max-width:${p}%;height:auto;`;
}
