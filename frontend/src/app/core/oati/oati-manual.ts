import {
  Manual,
  ManualBlock,
  OATI_STATIC_TYPES,
  OatiBlockType,
  isOatiFlowBlock,
  isOatiStaticBlock,
  isQuickGuideManual,
} from '../models/manual.models';

const STATIC_COUNT = OATI_STATIC_TYPES.length;

/** Muestra y edición en campos simples sin etiquetas HTML. */
export function stripHtmlToPlain(html: string): string {
  if (!html?.trim()) return '';
  if (!/<[a-z][\s\S]*>/i.test(html)) return html.trim();
  if (typeof document !== 'undefined') {
    const d = document.createElement('div');
    d.innerHTML = html;
    return (d.textContent || d.innerText || '').trim();
  }
  return html.replace(/<[^>]+>/gi, ' ').replace(/\s+/g, ' ').trim();
}

function nid(): string {
  return crypto.randomUUID();
}

export function defaultCoverData(): Record<string, unknown> {
  return {
    moduleHeaderLine: 'MÓDULO — TÍTULO DEL DOCUMENTO',
    macroProcess: 'Macroproceso: Gestión de Recursos',
    processLine: 'Proceso: de Apoyo',
    code: '',
    version: '01',
    approvalDate: '',
    centralTitle: 'TÍTULO CENTRAL DEL MANUAL',
    institutionLine: 'UNIVERSIDAD DISTRITAL FRANCISCO JOSÉ DE CALDAS',
    unitFooterLine: 'OFICINA ASESORA DE TECNOLOGÍAS E INFORMACIÓN',
    logoUdUrl: '',
    logoOatiUrl: '',
    logoUdData: '',
    logoOatiData: '',
    crestUrl: '',
    crestData: '',
    crestScalePercent: 100,
  };
}

export function defaultSectionData(): Record<string, unknown> {
  return {
    text: '',
    imageSrc: '',
    imageData: '',
    imageCaption: '',
    imageScalePercent: 100,
  };
}

export function defaultStepData(): Record<string, unknown> {
  return {
    title: '',
    description: '',
    imageSrc: '',
    imageData: '',
    imageCaption: '',
    imageScalePercent: 100,
  };
}

export function createDefaultOatiBlocks(): ManualBlock[] {
  const blocks: ManualBlock[] = [];
  let o = 0;
  for (const t of OATI_STATIC_TYPES) {
    if (t === 'oati_cover') {
      blocks.push({ id: nid(), type: t, order: o++, data: defaultCoverData() });
    } else {
      blocks.push({ id: nid(), type: t, order: o++, data: defaultSectionData() });
    }
  }

  blocks.push({
    id: nid(),
    type: 'oati_step',
    order: o++,
    data: {
      title: 'Ingreso al sistema',
      description:
        'Abra el navegador e ingrese al enlace indicado. Verifique el acceso con sus credenciales institucionales.',
      imageSrc: '',
      imageData: '',
      imageCaption: '',
      imageScalePercent: 100,
    },
  });
  blocks.push({
    id: nid(),
    type: 'oati_note',
    order: o++,
    data: {
      body: 'Use este espacio para observaciones o advertencias operativas.',
    },
  });
  return blocks;
}

/** Garantiza 6 bloques estáticos + deja flujo tal cual venga (o migra legacy). No altera guías rápidas. */
export function normalizeManual(manual: Manual): Manual {
  if (isQuickGuideManual(manual)) {
    return {
      ...manual,
      blocks: manual.blocks.map((b) => ({ ...b, data: { ...b.data } })),
      meta: { ...manual.meta },
    };
  }
  const hasModern = manual.blocks.some((b) => b.type === 'oati_cover');
  if (hasModern) {
    return ensureStaticShape(manual);
  }
  return migrateLegacyToOati(manual);
}

function ensureStaticShape(manual: Manual): Manual {
  const byType = new Map<string, ManualBlock>();
  for (const b of manual.blocks) {
    if (isOatiStaticBlock(b)) byType.set(b.type, b);
  }
  const flow = manual.blocks.filter((b) => isOatiFlowBlock(b)).sort((a, c) => a.order - c.order);

  const staticBlocks: ManualBlock[] = [];
  let order = 0;
  for (const t of OATI_STATIC_TYPES) {
    const found = byType.get(t);
    if (found) {
      if (t === 'oati_cover') {
        staticBlocks.push({
          ...found,
          data: { ...defaultCoverData(), ...found.data },
          order: order++,
        });
      } else {
        staticBlocks.push({
          ...found,
          data: { ...defaultSectionData(), ...found.data },
          order: order++,
        });
      }
    } else if (t === 'oati_cover') {
      staticBlocks.push({ id: nid(), type: 'oati_cover', order: order++, data: defaultCoverData() });
    } else {
      staticBlocks.push({ id: nid(), type: t, order: order++, data: defaultSectionData() });
    }
  }
  const merged = [
    ...staticBlocks,
    ...flow.map((b, i) => {
      const ord = STATIC_COUNT + i;
      if (b.type === 'oati_step') {
        return { ...b, order: ord, data: { ...defaultStepData(), ...b.data } };
      }
      return { ...b, order: ord };
    }),
  ];
  return { ...manual, blocks: merged };
}

function migrateLegacyToOati(manual: Manual): Manual {
  const findCover = manual.blocks.find((b) => b.type === 'cover');
  const coverData = findCover ? { ...findCover.data } : defaultCoverData();
  if (findCover) {
    coverData['moduleHeaderLine'] = String(coverData['moduleName'] ?? coverData['moduleHeaderLine'] ?? 'MÓDULO');
    coverData['centralTitle'] = String(coverData['manualTitle'] ?? coverData['centralTitle'] ?? 'TÍTULO');
    coverData['version'] = String(coverData['version'] ?? '01');
  }

  const texts: string[] = [];
  for (const b of [...manual.blocks].sort((a, c) => a.order - c.order)) {
    if (b.type === 'rich_text') texts.push(String(b.data['html'] ?? ''));
  }

  const pick = (i: number) => stripHtmlToPlain(texts[i] ?? '');

  const staticBlocks: ManualBlock[] = [
    { id: nid(), type: 'oati_cover', order: 0, data: coverData },
    { id: nid(), type: 'oati_intro', order: 1, data: { ...defaultSectionData(), text: pick(0) } },
    { id: nid(), type: 'oati_objective', order: 2, data: { ...defaultSectionData(), text: pick(1) } },
    { id: nid(), type: 'oati_scope', order: 3, data: { ...defaultSectionData(), text: pick(2) } },
    { id: nid(), type: 'oati_responsible', order: 4, data: { ...defaultSectionData(), text: pick(3) } },
    { id: nid(), type: 'oati_definitions', order: 5, data: { ...defaultSectionData(), text: pick(4) } },
  ];

  const flow: ManualBlock[] = [];
  let fo = STATIC_COUNT;
  for (const b of manual.blocks) {
    if (b.type === 'steps') {
      const items = (b.data['items'] as Array<{ title?: string; body?: string }>) ?? [];
      for (const it of items) {
        flow.push({
          id: nid(),
          type: 'oati_step',
          order: fo++,
          data: {
            title: it.title ?? 'Paso',
            description: it.body ?? '',
            imageSrc: '',
            imageData: '',
            imageCaption: '',
            imageScalePercent: 100,
          },
        });
      }
    }
    if (b.type === 'note') {
      flow.push({
        id: nid(),
        type: 'oati_note',
        order: fo++,
        data: { body: String(b.data['text'] ?? '') },
      });
    }
  }
  if (!flow.length) {
    flow.push({
      id: nid(),
      type: 'oati_step',
      order: 0,
      data: {
        title: 'Título del paso',
        description: 'Describa el procedimiento. Puede adjuntar una imagen de evidencia en el panel izquierdo.',
        imageSrc: '',
        imageData: '',
        imageCaption: '',
        imageScalePercent: 100,
      },
    });
    flow.push({
      id: nid(),
      type: 'oati_note',
      order: 0,
      data: { body: 'Texto de la nota (aparecerá con formato institucional).' },
    });
  }
  return {
    ...manual,
    blocks: [...staticBlocks, ...flow.map((b, i) => ({ ...b, order: STATIC_COUNT + i }))],
  };
}
export function needsOatiV2Migration(manual: Manual): boolean {
  if (isQuickGuideManual(manual)) return false;
  return !manual.blocks.some((b) => b.type === 'oati_cover');
}

export function getStaticBlock(manual: Manual, type: OatiBlockType): ManualBlock | undefined {
  return normalizeManual(manual).blocks.find((b) => b.type === type);
}

export function mergeFlowItems(staticBase: ManualBlock[], flow: ManualBlock[]): ManualBlock[] {
  const sortedFlow = [...flow].map((b, i) => ({
    ...b,
    type: b.type as OatiBlockType,
    order: STATIC_COUNT + i,
  }));
  return [...staticBase.map((b, i) => ({ ...b, order: i })), ...sortedFlow];
}

export function extractStaticBlocks(manual: Manual): ManualBlock[] {
  return normalizeManual(manual)
    .blocks.filter((b) => isOatiStaticBlock(b))
    .sort((a, b) => a.order - b.order);
}

export function extractFlowBlocks(manual: Manual): ManualBlock[] {
  return normalizeManual(manual)
    .blocks.filter((b) => isOatiFlowBlock(b))
    .sort((a, b) => a.order - b.order);
}
