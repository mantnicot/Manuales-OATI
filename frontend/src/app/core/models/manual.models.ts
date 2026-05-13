/** Tipos de bloque institucional OATI (v2). */
export type OatiBlockType =
  | 'oati_cover'
  | 'oati_intro'
  | 'oati_objective'
  | 'oati_scope'
  | 'oati_responsible'
  | 'oati_definitions'
  | 'oati_step'
  | 'oati_note';

/** Tipos heredados del MVP anterior (se migran al normalizar). */
export type LegacyBlockType =
  | 'cover'
  | 'toc'
  | 'heading1'
  | 'heading2'
  | 'heading3'
  | 'rich_text'
  | 'image'
  | 'steps'
  | 'table'
  | 'note'
  | 'separator'
  | 'link'
  | 'footer';

export type BlockType = OatiBlockType | LegacyBlockType;

export interface ManualBlock {
  id: string;
  type: BlockType;
  order: number;
  data: Record<string, unknown>;
}

export type ManualStatus = 'draft' | 'published' | 'archived';

export interface Manual {
  id: string;
  title: string;
  code: string;
  system_id: string | null;
  folder_id: string | null;
  status: ManualStatus;
  blocks: ManualBlock[];
  meta: Record<string, unknown>;
  current_version: number;
  created_at: string | null;
  updated_at: string | null;
}

/** Documento guardado solo como PDF subido (no editable en el constructor OATI). */
export function isPdfStorageManual(m: Pick<Manual, 'meta'>): boolean {
  return m.meta?.['storage_kind'] === 'pdf';
}

export const OATI_STATIC_TYPES: readonly OatiBlockType[] = [
  'oati_cover',
  'oati_intro',
  'oati_objective',
  'oati_scope',
  'oati_responsible',
  'oati_definitions',
] as const;

export const OATI_FLOW_TYPES: readonly OatiBlockType[] = ['oati_step', 'oati_note'] as const;

export function isOatiStaticBlock(b: ManualBlock): boolean {
  return (OATI_STATIC_TYPES as readonly string[]).includes(b.type);
}

export function isOatiFlowBlock(b: ManualBlock): boolean {
  return b.type === 'oati_step' || b.type === 'oati_note';
}
