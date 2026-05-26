import { NgFor, NgIf } from '@angular/common';
import { Component, computed, DestroyRef, effect, inject, signal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { debounceTime, Subject } from 'rxjs';

import { ManualBlock, isPdfStorageManual, isQuickGuideManual } from '../../core/models/manual.models';
import { ManualApiService } from '../../core/services/manual-api.service';
import { PdfBrowserService } from '../../core/services/pdf-browser.service';
import { ManualEditorStore } from '../editor/manual-editor.store';

type QgTheme = 'glossary' | 'guide';
type QgComponentKind = 'glossary' | 'step' | 'comment';

type MiniStepRow = {
  text: string;
  imageData: string;
  imageData2: string;
  imageFileName: string;
  imageFileName2: string;
};

@Component({
  selector: 'app-quick-guide-editor',
  standalone: true,
  providers: [ManualEditorStore],
  templateUrl: './quick-guide-editor.component.html',
  styleUrl: './quick-guide-editor.component.scss',
  imports: [
    NgIf,
    NgFor,
    RouterLink,
    FormsModule,
    MatToolbarModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSnackBarModule,
    MatTooltipModule,
  ],
})
export class QuickGuideEditorComponent {
  /** Evita reinstanciar filas del glosario al mutar el documento (mantiene foco y edición estable). */
  readonly trackByGlossaryIdx = (idx: number, _e: { term: string; definition: string }) => idx;
  readonly trackByMiniIdx = (idx: number, _ms: MiniStepRow) => idx;

  readonly store = inject(ManualEditorStore);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly snack = inject(MatSnackBar);
  private readonly api = inject(ManualApiService);
  private readonly pdfBrowser = inject(PdfBrowserService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly persist$ = new Subject<void>();

  readonly selectedPageIdx = signal(0);
  readonly selectedPlacedIdx = signal(-1);
  readonly previewHtml = signal('');
  readonly dragTmp = signal<{ pageIdx: number; ci: number; x: number; y: number } | null>(null);
  readonly resizeTmp = signal<{ pageIdx: number; ci: number; w: number; h: number } | null>(null);

  private previewTimer: ReturnType<typeof setTimeout> | null = null;
  private previewHtmlObjectUrl: string | null = null;

  /** Vista previa HTML vía URL blob (más fiable que `srcdoc` con documentos grandes o recursos embebidos). */
  readonly previewIframeSrc = signal<SafeResourceUrl | null>(null);

  readonly pageBlocks = computed(() => {
    const m = this.store.manual();
    if (!m) return [];
    return [...m.blocks].filter((b) => b.type === 'qg_page').sort((a, b) => a.order - b.order);
  });

  readonly selectedPage = computed(() => {
    const list = this.pageBlocks();
    const i = this.selectedPageIdx();
    return list[i] ?? null;
  });

  readonly activeComponentKind = computed((): QgComponentKind => {
    const si = this.selectedPlacedIdx();
    if (si < 0) return 'step';
    const k = String(columnComponent(this.pageBlocks()[this.selectedPageIdx()], si)['kind'] || 'step');
    if (k === 'glossary' || k === 'comment' || k === 'step') return k;
    return 'step';
  });

  constructor() {
    this.destroyRef.onDestroy(() => this.revokePreviewHtmlBlob());

    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((pm) => {
      const id = pm.get('id');
      if (!id) return;
      void this.store.load(id).then(() => this.afterLoad(id));
    });

    this.persist$.pipe(debounceTime(2000), takeUntilDestroyed(this.destroyRef)).subscribe(async () => {
      if (!this.store.dirty()) return;
      await this.store.save(false);
      const m = this.store.manual();
      if (m && !this.store.error()) {
        this.snack.open('Guardado automático', 'Cerrar', { duration: 1600 });
      }
    });

    effect(() => {
      const m = this.store.manual();
      const blocks = m?.blocks;
      if (!m || !blocks) {
        untracked(() => this.previewHtml.set(''));
        return;
      }
      void blocks;
      void m.current_version;
      void m.meta;
      untracked(() => this.queuePreviewRefresh());
    });

    effect(() => {
      const h = this.previewHtml();
      untracked(() => this.syncPreviewIframeFromHtml(h));
    });
  }

  openHtmlPreviewInBrowser(manualId: string): void {
    this.pdfBrowser.openHtmlPreviewInNewTab(manualId);
  }

  openPdfInBrowser(manualId: string): void {
    this.pdfBrowser.openGeneratedPdfInNewTab(manualId);
  }

  private queuePreviewRefresh(): void {
    if (this.previewTimer) clearTimeout(this.previewTimer);
    this.previewTimer = setTimeout(() => {
      this.previewTimer = null;
      this.fetchServerPreview();
    }, 500);
  }

  private fetchServerPreview(): void {
    const m = this.store.manual();
    if (!m) return;
    this.api
      .renderPreviewHtml({
        title: m.title,
        code: m.code,
        blocks: m.blocks,
        meta: m.meta,
        current_version: m.current_version,
      })
      .subscribe({
        next: (html) => this.previewHtml.set(html),
        error: () => {
          this.previewHtml.set('');
          this.snack.open(
            'No se pudo generar la vista previa HTML. Compruebe que el API esté en marcha y que `ng serve` use el proxy.',
            'Cerrar',
            { duration: 9000 },
          );
        },
      });
  }

  private afterLoad(id: string): void {
    const m = this.store.manual();
    if (!m) {
      this.snack.open('No se pudo abrir el documento.', 'Cerrar', { duration: 5000 });
      void this.router.navigate(['/']);
      return;
    }
    if (isPdfStorageManual(m)) {
      this.snack.open('Este PDF no se edita como guía rápida.', 'Cerrar', { duration: 6000 });
      void this.router.navigate(['/']);
      return;
    }
    if (!isQuickGuideManual(m)) {
      void this.router.navigate(['/manual', id], { replaceUrl: true });
      return;
    }
    if (m.meta['document_kind'] !== 'quick_guide') {
      this.store.mergeMeta({ document_kind: 'quick_guide' });
    }
    this.migrateLayoutsIfMissing();
    this.selectedPageIdx.set(0);
    this.selectedPlacedIdx.set(-1);
    this.fetchServerPreview();
  }

  private revokePreviewHtmlBlob(): void {
    if (this.previewHtmlObjectUrl) {
      URL.revokeObjectURL(this.previewHtmlObjectUrl);
      this.previewHtmlObjectUrl = null;
    }
    this.previewIframeSrc.set(null);
  }

  private syncPreviewIframeFromHtml(html: string): void {
    this.revokePreviewHtmlBlob();
    if (!html.trim()) return;
    const origin = window.location.origin;
    const rewritten = html
      .replace(/href="\/api\/v1\//g, `href="${origin}/api/v1/`)
      .replace(/src="\/api\/v1\//g, `src="${origin}/api/v1/`);
    const blob = new Blob([rewritten], { type: 'text/html;charset=utf-8' });
    this.previewHtmlObjectUrl = URL.createObjectURL(blob);
    this.previewIframeSrc.set(this.sanitizer.bypassSecurityTrustResourceUrl(this.previewHtmlObjectUrl));
  }

  onSelectPageTab(i: number): void {
    this.selectedPageIdx.set(i);
    this.selectedPlacedIdx.set(-1);
    this.dragTmp.set(null);
    this.resizeTmp.set(null);
  }

  clearPlacedSelection(): void {
    this.selectedPlacedIdx.set(-1);
  }

  displayPlacement(pageIdx: number, ci: number): { x: number; y: number; w: number; h: number; z: number } {
    const d = this.dragTmp();
    const r = this.resizeTmp();
    const col = getColumnRaw(this.pageBlocks()[pageIdx], ci);
    let x = Number(col?.['xPct'] ?? 0);
    let y = Number(col?.['yPct'] ?? 0);
    let w = Math.max(8, Math.min(100, Number(col?.['widthPct'] ?? 30)));
    let h = Math.max(10, Math.min(92, Number(col?.['heightPct'] ?? 40)));
    const z = Number(col?.['zIndex'] ?? ci);
    if (d && d.pageIdx === pageIdx && d.ci === ci) {
      x = d.x;
      y = d.y;
    }
    if (r && r.pageIdx === pageIdx && r.ci === ci) {
      w = r.w;
      h = r.h;
    }
    return { x, y, w, h, z };
  }

  placedKindLabel(ci: number): string {
    const k = String(columnComponent(this.pageBlocks()[this.selectedPageIdx()], ci)['kind'] || '');
    if (k === 'glossary') return 'Glosario';
    if (k === 'comment') return 'Nota';
    return 'Paso';
  }

  placedSummary(ci: number): string {
    const comp = columnComponent(this.pageBlocks()[this.selectedPageIdx()], ci);
    const k = String(comp['kind'] || '');
    if (k === 'glossary') {
      const ent = comp['entries'];
      const n = Array.isArray(ent) ? ent.length : 0;
      return `${n} términos`;
    }
    if (k === 'comment') {
      const t = String(comp['text'] || '').trim();
      return t.length > 48 ? t.slice(0, 48) + '…' : t || 'Vacío';
    }
    if (k === 'step') {
      const title = String(comp['title'] || '').trim();
      const mini = comp['miniSteps'] || comp['mini_steps'];
      let firstTxt = '';
      if (Array.isArray(mini) && mini.length > 0) {
        const row = mini[0] as Record<string, unknown>;
        firstTxt = String(row['text'] || '').trim();
      }
      if (title && firstTxt) {
        const combo = `${title}: ${firstTxt}`;
        return combo.length > 180 ? combo.slice(0, 180) + '…' : combo;
      }
      return title || firstTxt || 'Sin título';
    }
    const t = String(comp['title'] || '').trim();
    return t || 'Sin título';
  }

  /** Vista compacta de términos del glosario en el lienzo. */
  glossaryPreviewForPlaced(ci: number): { term: string; definition: string }[] {
    const page = this.pageBlocks()[this.selectedPageIdx()];
    const comp = columnComponent(page, ci);
    if (String(comp['kind'] || '').toLowerCase() !== 'glossary') return [];
    const raw = comp['entries'];
    if (!Array.isArray(raw)) return [];
    const out: { term: string; definition: string }[] = [];
    for (const e of raw) {
      if (!e || typeof e !== 'object') continue;
      const r = e as Record<string, unknown>;
      const term = String(r['term'] ?? '').trim();
      const definition = String(r['definition'] ?? r['text'] ?? '').trim();
      if (!term && !definition) continue;
      const defShort = definition.length > 72 ? definition.slice(0, 72) + '…' : definition;
      out.push({ term: term || '—', definition: defShort });
      if (out.length >= 8) break;
    }
    return out;
  }

  /** Primera imagen del módulo (paso o comentario) para miniatura en el lienzo. */
  thumbForPlaced(ci: number): SafeResourceUrl | null {
    const raw = this.placedPreviewImageRaw(ci);
    return raw ? this.sanitizer.bypassSecurityTrustResourceUrl(raw) : null;
  }

  private placedPreviewImageRaw(ci: number): string | null {
    const page = this.pageBlocks()[this.selectedPageIdx()];
    const comp = columnComponent(page, ci);
    const k = String(comp['kind'] || '');
    const normalizeImg = (s: string) => {
      const t = s.trim();
      if (!t) return '';
      return t.startsWith('data:') ? t.replace(/\s+/g, '') : t;
    };
    if (k === 'comment') {
      const img = normalizeImg(String(comp['imageData'] || comp['image_data'] || ''));
      return img || null;
    }
    if (k === 'step') {
      const mini = comp['miniSteps'] || comp['mini_steps'];
      if (!Array.isArray(mini)) return null;
      for (const row of mini) {
        const r = row as Record<string, unknown>;
        const a = normalizeImg(String(r['imageData'] || r['image_data'] || ''));
        if (a) return a;
        const b = normalizeImg(String(r['imageData2'] || r['image_data2'] || ''));
        if (b) return b;
      }
    }
    return null;
  }

  beginDrag(ev: PointerEvent, pageIdx: number, ci: number): void {
    ev.preventDefault();
    ev.stopPropagation();
    this.selectPlaced(ci, false);
    const body = (ev.currentTarget as HTMLElement).closest('.sheet-body-preview') as HTMLElement | null;
    if (!body) return;
    const rect = body.getBoundingClientRect();
    const col = getColumnRaw(this.pageBlocks()[pageIdx], ci);
    if (!col) return;
    const ow = Math.max(8, Math.min(100, Number(col['widthPct'] ?? 30)));
    const oh = Math.max(10, Math.min(92, Number(col['heightPct'] ?? 40)));
    const ox = Math.max(0, Math.min(100 - ow, Number(col['xPct'] ?? 0)));
    const oy = Math.max(0, Math.min(100 - oh, Number(col['yPct'] ?? 0)));
    const sx = ev.clientX;
    const sy = ev.clientY;

    const move = (e: PointerEvent) => {
      const dxPct = ((e.clientX - sx) / rect.width) * 100;
      const dyPct = ((e.clientY - sy) / rect.height) * 100;
      const nx = Math.max(0, Math.min(100 - ow, ox + dxPct));
      const ny = Math.max(0, Math.min(100 - oh, oy + dyPct));
      this.dragTmp.set({ pageIdx, ci, x: nx, y: ny });
    };
    const up = () => {
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', up);
      const d = this.dragTmp();
      if (d) {
        this.patchPlacement(pageIdx, ci, { xPct: d.x, yPct: d.y });
      }
      this.dragTmp.set(null);
    };
    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', up);
    this.dragTmp.set({ pageIdx, ci, x: ox, y: oy });
  }

  /** Redimensionar solo desde la esquina inferior derecha. */
  beginResize(ev: PointerEvent, pageIdx: number, ci: number): void {
    ev.preventDefault();
    ev.stopPropagation();
    this.selectPlaced(ci, false);
    const body = (ev.currentTarget as HTMLElement).closest('.sheet-body-preview') as HTMLElement | null;
    if (!body) return;
    const rect = body.getBoundingClientRect();
    const col = getColumnRaw(this.pageBlocks()[pageIdx], ci);
    if (!col) return;
    const ox = Number(col['xPct'] ?? 0);
    const oy = Number(col['yPct'] ?? 0);
    const ow = Math.max(8, Math.min(100, Number(col['widthPct'] ?? 30)));
    const oh = Math.max(10, Math.min(92, Number(col['heightPct'] ?? 40)));
    const sx = ev.clientX;
    const sy = ev.clientY;

    const move = (e: PointerEvent) => {
      const dxPct = ((e.clientX - sx) / rect.width) * 100;
      const dyPct = ((e.clientY - sy) / rect.height) * 100;
      const nw = Math.max(8, Math.min(100 - ox, ow + dxPct));
      const nh = Math.max(10, Math.min(100 - oy, oh + dyPct));
      this.resizeTmp.set({ pageIdx, ci, w: nw, h: nh });
    };
    const up = () => {
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerup', up);
      const r = this.resizeTmp();
      if (r) {
        this.patchPlacement(pageIdx, ci, { widthPct: r.w, heightPct: r.h });
      }
      this.resizeTmp.set(null);
    };
    document.addEventListener('pointermove', move);
    document.addEventListener('pointerup', up);
    this.resizeTmp.set({ pageIdx, ci, w: ow, h: oh });
  }

  selectPlaced(ci: number, bumpZ = true): void {
    this.selectedPlacedIdx.set(ci);
    if (!bumpZ) return;
    const pi = this.selectedPageIdx();
    const cols = (this.pageBlocks()[pi]?.data['columns'] as Record<string, unknown>[]) || [];
    const maxZ = cols.reduce((m, c) => Math.max(m, Number(c['zIndex'] ?? 0)), -1);
    this.patchPlacement(pi, ci, { zIndex: maxZ + 1 });
  }

  placementField(pageIdx: number, ci: number, key: 'xPct' | 'yPct' | 'widthPct' | 'heightPct'): number {
    const c = getColumnRaw(this.pageBlocks()[pageIdx], ci);
    if (!c) {
      if (key === 'widthPct') return 30;
      if (key === 'heightPct') return 40;
      return 0;
    }
    if (key === 'heightPct') return Number(c['heightPct'] ?? 40);
    return Number(c[key] ?? (key === 'widthPct' ? 30 : 0));
  }

  componentField(key: string): string {
    const si = this.selectedPlacedIdx();
    if (si < 0) return '';
    const comp = columnComponent(this.pageBlocks()[this.selectedPageIdx()], si);
    return String(comp[key] ?? '');
  }

  markDirtyPersist(): void {
    this.persist$.next();
  }

  patchTitleCode(title: string, code: string): void {
    this.store.patchManualMeta({ title, code });
    this.markDirtyPersist();
  }

  private writeQgPages(nextPages: ManualBlock[]): void {
    const m = this.store.manual();
    if (!m) return;
    const rest = m.blocks.filter((b) => b.type !== 'qg_page');
    const ordered = nextPages.map((b, i) => ({ ...b, order: i }));
    this.store.patchBlocks([...rest, ...ordered]);
    this.markDirtyPersist();
  }

  addPage(theme: QgTheme): void {
    const pages = this.pageBlocks();
    const nb = newQgPageBlock(theme, pages.length);
    this.writeQgPages([...pages, nb]);
    this.selectedPageIdx.set(pages.length);
    this.selectedPlacedIdx.set(-1);
    this.snack.open('Página agregada', 'Cerrar', { duration: 2000 });
  }

  removePage(idx: number): void {
    const pages = this.pageBlocks();
    if (pages.length <= 1) {
      this.snack.open('Debe quedar al menos una página.', 'Cerrar', { duration: 4000 });
      return;
    }
    const next = pages.filter((_, i) => i !== idx);
    this.writeQgPages(next);
    const newIdx = Math.min(idx, next.length - 1);
    this.selectedPageIdx.set(newIdx);
    this.selectedPlacedIdx.set(-1);
  }

  movePage(idx: number, dir: -1 | 1): void {
    const pages = [...this.pageBlocks()];
    const j = idx + dir;
    if (j < 0 || j >= pages.length) return;
    [pages[idx], pages[j]] = [pages[j], pages[idx]];
    this.writeQgPages(pages);
    this.selectedPageIdx.set(j);
  }

  patchPageData(idx: number, data: Record<string, unknown>): void {
    const pages = [...this.pageBlocks()];
    const cur = pages[idx];
    if (!cur) return;
    pages[idx] = { ...cur, data: { ...cur.data, ...data } };
    this.writeQgPages(pages);
  }

  patchPlacement(
    pageIdx: number,
    colIdx: number,
    p: { xPct?: number; yPct?: number; widthPct?: number; heightPct?: number; zIndex?: number },
  ): void {
    const pages = [...this.pageBlocks()];
    const pg = pages[pageIdx];
    if (!pg) return;
    const cols = [...((pg.data['columns'] as Record<string, unknown>[]) || [])].map((c) => ({ ...c }));
    const c = { ...cols[colIdx] };
    if (p.xPct !== undefined) c['xPct'] = Math.max(0, Math.min(100, Number(p.xPct)));
    if (p.yPct !== undefined) c['yPct'] = Math.max(0, Math.min(100, Number(p.yPct)));
    if (p.widthPct !== undefined) {
      const n = Number(p.widthPct);
      c['widthPct'] = Number.isFinite(n) ? Math.max(8, Math.min(100, n)) : 30;
    }
    if (p.heightPct !== undefined) {
      const n = Number(p.heightPct);
      c['heightPct'] = Number.isFinite(n) ? Math.max(10, Math.min(92, n)) : 40;
    }
    if (p.zIndex !== undefined) c['zIndex'] = Number(p.zIndex);
    const w = Number(c['widthPct'] ?? 30);
    const h = Number(c['heightPct'] ?? 40);
    let x = Number(c['xPct'] ?? 0);
    let y = Number(c['yPct'] ?? 0);
    x = Math.min(Math.max(0, x), 100 - w);
    y = Math.min(Math.max(0, y), 100 - h);
    c['xPct'] = x;
    c['yPct'] = y;
    cols[colIdx] = c;
    pages[pageIdx] = { ...pg, data: { ...pg.data, columns: cols } };
    this.writeQgPages(pages);
  }

  patchColumn(
    pageIdx: number,
    colIdx: number,
    patch: { widthPct?: number; component?: Record<string, unknown> },
  ): void {
    const pages = [...this.pageBlocks()];
    const p = pages[pageIdx];
    if (!p) return;
    const cols = [...((p.data['columns'] as Record<string, unknown>[]) || [])];
    const c = { ...(cols[colIdx] ?? {}) };
    if (patch.widthPct != null) {
      const n = Number(patch.widthPct);
      c['widthPct'] = Number.isFinite(n) ? Math.max(8, Math.min(100, n)) : 100;
    }
    if (patch.component) {
      const prev = (c['component'] as Record<string, unknown> | undefined) ?? {};
      c['component'] = { ...prev, ...patch.component };
    }
    cols[colIdx] = c;
    pages[pageIdx] = { ...p, data: { ...p.data, columns: cols } };
    this.writeQgPages(pages);
  }

  setComponentKind(pageIdx: number, colIdx: number, kind: QgComponentKind): void {
    this.patchColumn(pageIdx, colIdx, { component: defaultComponent(kind) });
  }

  addModule(pageIdx: number): void {
    const pages = [...this.pageBlocks()];
    const p = pages[pageIdx];
    if (!p) return;
    const cols = [...((p.data['columns'] as Record<string, unknown>[]) || [])];
    const n = cols.length;
    const y = Math.min(72, 8 + (n % 4) * 14);
    const x = 4 + ((n * 7) % 40);
    cols.push({
      xPct: x,
      yPct: y,
      widthPct: 28,
      heightPct: 40,
      zIndex: n,
      component: defaultComponent('step'),
    });
    pages[pageIdx] = { ...p, data: { ...p.data, columns: cols } };
    this.writeQgPages(pages);
    this.selectedPlacedIdx.set(cols.length - 1);
  }

  addColumn(pageIdx: number): void {
    this.addModule(pageIdx);
  }

  removeColumn(pageIdx: number, colIdx: number): void {
    const pages = [...this.pageBlocks()];
    const p = pages[pageIdx];
    if (!p) return;
    const cols = [...((p.data['columns'] as Record<string, unknown>[]) || [])];
    if (cols.length <= 1) {
      this.snack.open('Debe haber al menos un módulo.', 'Cerrar', { duration: 4000 });
      return;
    }
    cols.splice(colIdx, 1);
    pages[pageIdx] = { ...p, data: { ...p.data, columns: cols } };
    this.writeQgPages(pages);
    const sel = this.selectedPlacedIdx();
    if (sel === colIdx) this.selectedPlacedIdx.set(-1);
    else if (sel > colIdx) this.selectedPlacedIdx.set(sel - 1);
  }

  migrateLayoutsIfMissing(): void {
    const pages = this.pageBlocks();
    let anyChanged = false;
    const next = pages.map((pg) => {
      let pageChanged = false;
      const cols = [...((pg.data['columns'] as Record<string, unknown>[]) || [])];
      cols.forEach((c, i) => {
        const hasX = c['xPct'] != null || c['x_pct'] != null;
        const hasY = c['yPct'] != null || c['y_pct'] != null;
        if (!hasX || !hasY) {
          pageChanged = true;
          const row = Math.floor(i / 3);
          const col = i % 3;
          c['xPct'] = 2 + col * 32;
          c['yPct'] = 6 + row * 42;
        }
        if (c['zIndex'] == null && c['z_index'] == null) {
          pageChanged = true;
          c['zIndex'] = i;
        }
        if (c['widthPct'] == null && c['width_pct'] == null) {
          pageChanged = true;
          c['widthPct'] = 30;
        }
        if (c['heightPct'] == null && c['height_pct'] == null) {
          pageChanged = true;
          c['heightPct'] = 40;
        }
      });
      if (pageChanged) anyChanged = true;
      return pageChanged ? { ...pg, data: { ...pg.data, columns: cols } } : pg;
    });
    if (anyChanged) this.writeQgPages(next);
  }

  glossaryEntries(pageIdx: number, colIdx: number): { term: string; definition: string }[] {
    const pages = this.pageBlocks();
    const comp = columnComponent(pages[pageIdx], colIdx);
    const raw = comp['entries'];
    if (!Array.isArray(raw)) return [];
    return raw.map((e) => ({
      term: String((e as Record<string, unknown>)?.['term'] ?? ''),
      definition: String((e as Record<string, unknown>)?.['definition'] ?? ''),
    }));
  }

  setGlossaryEntries(pageIdx: number, colIdx: number, entries: { term: string; definition: string }[]): void {
    this.patchColumn(pageIdx, colIdx, { component: { entries } });
  }

  updateGlossaryEntry(
    pageIdx: number,
    colIdx: number,
    entryIdx: number,
    field: 'term' | 'definition',
    value: string,
  ): void {
    const cur = this.glossaryEntries(pageIdx, colIdx);
    const next = cur.map((e, j) => (j === entryIdx ? { ...e, [field]: value } : e));
    this.setGlossaryEntries(pageIdx, colIdx, next);
  }

  setMiniImage(pageIdx: number, colIdx: number, mi: number, which: 1 | 2, data: string, fileName = ''): void {
    const ms = this.miniSteps(pageIdx, colIdx);
    const key = which === 1 ? 'imageData' : 'imageData2';
    const fnKey = which === 1 ? 'imageFileName' : 'imageFileName2';
    const next = ms.map((x, j) =>
      j === mi ? { ...x, [key]: data, [fnKey]: data ? fileName : '' } : x,
    );
    this.setMiniSteps(pageIdx, colIdx, next);
  }

  clearMiniImage(pageIdx: number, colIdx: number, mi: number, which: 1 | 2): void {
    this.setMiniImage(pageIdx, colIdx, mi, which, '', '');
  }

  addGlossaryEntry(pageIdx: number, colIdx: number): void {
    const cur = this.glossaryEntries(pageIdx, colIdx);
    this.setGlossaryEntries(pageIdx, colIdx, [...cur, { term: '', definition: '' }]);
  }

  removeGlossaryEntry(pageIdx: number, colIdx: number, entryIdx: number): void {
    const cur = this.glossaryEntries(pageIdx, colIdx);
    this.setGlossaryEntries(
      pageIdx,
      colIdx,
      cur.filter((_, j) => j !== entryIdx),
    );
  }

  addMiniStepRow(pageIdx: number, colIdx: number): void {
    const cur = this.miniSteps(pageIdx, colIdx);
    this.setMiniSteps(pageIdx, colIdx, [...cur, emptyMiniStep()]);
  }

  updateMiniStepText(pageIdx: number, colIdx: number, mi: number, text: string): void {
    const cur = this.miniSteps(pageIdx, colIdx);
    const next = cur.map((x, j) => (j === mi ? { ...x, text } : x));
    this.setMiniSteps(pageIdx, colIdx, next);
  }

  miniSteps(pageIdx: number, colIdx: number): MiniStepRow[] {
    const pages = this.pageBlocks();
    const comp = columnComponent(pages[pageIdx], colIdx);
    const raw = comp['miniSteps'];
    if (!Array.isArray(raw)) return [];
    return raw.map((row) => {
      const r = row as Record<string, unknown>;
      return {
        text: String(r['text'] ?? ''),
        imageData: String(r['imageData'] ?? r['image_data'] ?? ''),
        imageData2: String(r['imageData2'] ?? r['image_data2'] ?? ''),
        imageFileName: String(r['imageFileName'] ?? r['image_file_name'] ?? ''),
        imageFileName2: String(r['imageFileName2'] ?? r['image_file_name2'] ?? ''),
      };
    });
  }

  setMiniSteps(pageIdx: number, colIdx: number, mini: MiniStepRow[]): void {
    this.patchColumn(pageIdx, colIdx, { component: { miniSteps: mini } });
  }

  async saveNow(bump: boolean): Promise<void> {
    await this.store.save(bump);
    if (this.store.error()) {
      this.snack.open(this.store.error() ?? 'Error al guardar', 'Cerrar', { duration: 6000 });
      return;
    }
    this.snack.open('Cambios guardados', 'Cerrar', { duration: 2500 });
  }

  /** MIME vacío es habitual en algunos navegadores/Windows; usamos también la extensión. */
  private isProbablyImageFile(f: File): boolean {
    const t = (f.type ?? '').trim();
    if (t.startsWith('image/')) return true;
    return /\.(png|jpe?g|jfif|gif|webp|bmp|svg|tif|tiff|avif|hei[cf]|ico)$/i.test(f.name);
  }

  readFileAsData(ev: Event, onData: (data: string, fileName: string) => void): void {
    const input = ev.target as HTMLInputElement;
    const f = input.files?.[0];
    const clearInput = () => {
      input.value = '';
    };
    if (!f) return;
    if (!this.isProbablyImageFile(f)) {
      clearInput();
      this.snack.open('Seleccione un archivo de imagen (PNG, JPG, GIF, WEBP…).', 'Cerrar', { duration: 5000 });
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      clearInput();
      const d = String(reader.result ?? '');
      if (!d) {
        this.snack.open('No se pudo leer la imagen.', 'Cerrar', { duration: 5000 });
        return;
      }
      onData(d, f.name);
    };
    reader.onerror = () => {
      clearInput();
      this.snack.open('Error al leer el archivo.', 'Cerrar', { duration: 5000 });
    };
    reader.readAsDataURL(f);
  }

  onStepImage(ev: Event, pageIdx: number, colIdx: number, mi: number, which: 1 | 2): void {
    this.readFileAsData(ev, (d, name) => this.setMiniImage(pageIdx, colIdx, mi, which, d, name));
  }

  onCommentImage(ev: Event, pageIdx: number, colIdx: number): void {
    this.readFileAsData(ev, (d, name) =>
      this.patchColumn(pageIdx, colIdx, { component: { imageData: d, imageFileName: name } }),
    );
  }
}

function getColumnRaw(page: ManualBlock | undefined, colIdx: number): Record<string, unknown> | null {
  if (!page) return null;
  const cols = page.data['columns'];
  if (!Array.isArray(cols) || !cols[colIdx]) return null;
  return cols[colIdx] as Record<string, unknown>;
}

function columnComponent(page: ManualBlock | undefined, colIdx: number): Record<string, unknown> {
  const c = getColumnRaw(page, colIdx);
  if (!c) return {};
  const comp = c['component'];
  return typeof comp === 'object' && comp != null ? { ...(comp as Record<string, unknown>) } : {};
}

function defaultComponent(kind: QgComponentKind): Record<string, unknown> {
  if (kind === 'glossary') {
    return {
      kind: 'glossary',
      entries: [
        { term: '', definition: '' },
        { term: '', definition: '' },
      ],
    };
  }
  if (kind === 'comment') {
    return { kind: 'comment', text: '', imageData: '', imageFileName: '' };
  }
  return {
    kind: 'step',
    title: 'NUEVO PASO',
    miniSteps: [emptyMiniStep()],
  };
}

function emptyMiniStep(): MiniStepRow {
  return { text: '', imageData: '', imageData2: '', imageFileName: '', imageFileName2: '' };
}

function newQgPageBlock(theme: QgTheme, order: number): ManualBlock {
  const id = crypto.randomUUID();
  if (theme === 'glossary') {
    return {
      id,
      type: 'qg_page',
      order,
      data: {
        headerTitle: 'GLOSARIO',
        theme: 'glossary',
        columns: [
          {
            xPct: 2,
            yPct: 3,
            widthPct: 96,
            heightPct: 88,
            zIndex: 0,
            component: defaultComponent('glossary'),
          },
        ],
      },
    };
  }
  return {
    id,
    type: 'qg_page',
    order,
    data: {
      headerTitle: 'GUÍA RÁPIDA',
      theme: 'guide',
      columns: [
        {
          xPct: 3,
          yPct: 8,
          widthPct: 30,
          heightPct: 78,
          zIndex: 0,
          component: defaultComponent('step'),
        },
        {
          xPct: 35,
          yPct: 8,
          widthPct: 30,
          heightPct: 78,
          zIndex: 1,
          component: defaultComponent('step'),
        },
        {
          xPct: 68,
          yPct: 8,
          widthPct: 29,
          heightPct: 78,
          zIndex: 2,
          component: defaultComponent('comment'),
        },
      ],
    },
  };
}
