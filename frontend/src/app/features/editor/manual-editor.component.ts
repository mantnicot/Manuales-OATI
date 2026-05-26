import { CdkDragDrop, DragDropModule, moveItemInArray } from '@angular/cdk/drag-drop';
import { NgFor, NgIf } from '@angular/common';
import {
  Component,
  computed,
  DestroyRef,
  ElementRef,
  HostListener,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDividerModule } from '@angular/material/divider';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatToolbarModule } from '@angular/material/toolbar';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import {
  catchError,
  debounceTime,
  interval,
  map,
  merge,
  of,
  Subject,
  switchMap,
} from 'rxjs';

import { manualToPreviewHtml } from '../../core/preview/document-preview';
import { Manual, ManualBlock, OatiBlockType, isPdfStorageManual, isQuickGuideManual } from '../../core/models/manual.models';
import { ManualApiService } from '../../core/services/manual-api.service';
import {
  extractFlowBlocks,
  extractStaticBlocks,
  mergeFlowItems,
  normalizeManual,
  needsOatiV2Migration,
  stripHtmlToPlain,
} from '../../core/oati/oati-manual';
import { imageScalePercent } from '../../core/oati/oati-images';
import { ManualEditorStore } from './manual-editor.store';

@Component({
  selector: 'app-manual-editor',
  standalone: true,
  providers: [ManualEditorStore],
  templateUrl: './manual-editor.component.html',
  styleUrl: './manual-editor.component.scss',
  imports: [
    NgIf,
    NgFor,
    RouterLink,
    FormsModule,
    DragDropModule,
    MatToolbarModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatDividerModule,
    MatFormFieldModule,
    MatInputModule,
    MatSnackBarModule,
  ],
})
export class ManualEditorComponent {
  readonly previewFrame = viewChild<ElementRef<HTMLIFrameElement>>('previewFrame');
  readonly store = inject(ManualEditorStore);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly snack = inject(MatSnackBar);
  private readonly api = inject(ManualApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly bump$ = new Subject<void>();
  private readonly persistDraft$ = new Subject<void>();
  private readonly preview$ = new Subject<{ doc: Document; scrollTop: number; snapshot: Manual }>();
  private previewTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly draftKeyPrefix = 'oati-manual-draft:';

  readonly flowItems = signal<ManualBlock[]>([]);
  readonly selectedStatic = signal<OatiBlockType>('oati_cover');
  readonly selectedFlowId = signal<string | null>(null);
  readonly activePanel = signal<'static' | 'flow'>('static');

  readonly staticDefs: { type: OatiBlockType; label: string }[] = [
    { type: 'oati_cover', label: '1. Portada' },
    { type: 'oati_intro', label: '2. Introducción' },
    { type: 'oati_objective', label: '3. Objetivo' },
    { type: 'oati_scope', label: '4. Alcance' },
    { type: 'oati_responsible', label: '5. Responsables' },
    { type: 'oati_definitions', label: '6. Definiciones y siglas' },
  ];

  readonly palette: { label: string; kind: 'oati_step' | 'oati_note' }[] = [
    { label: '7. Paso a paso', kind: 'oati_step' },
    { label: '8. Nota', kind: 'oati_note' },
  ];

  readonly selectedFlowBlock = computed(() => {
    const id = this.selectedFlowId();
    if (!id) return null;
    return this.flowItems().find((b) => b.id === id) ?? null;
  });

  constructor() {
    this.destroyRef.onDestroy(() => {
      if (this.previewTimer) clearTimeout(this.previewTimer);
    });

    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((pm) => {
      const id = pm.get('id');
      if (!id) return;
      void this.store.load(id).then(() => {
        const m = this.store.manual();
        if (!m) return;
        if (isPdfStorageManual(m)) {
          this.snack.open(
            'Este documento está guardado solo como PDF. Ábralo desde la biblioteca (icono de ver o descarga).',
            'Entendido',
            { duration: 7000 },
          );
          void this.router.navigate(['/']);
          return;
        }
        if (isQuickGuideManual(m)) {
          void this.router.navigate(['/quick-guide', id], { replaceUrl: true });
          return;
        }
        this.afterManualReady();
      });
    });

    this.preview$
      .pipe(
        switchMap(({ doc, scrollTop, snapshot }) => {
          const w = normalizeManual(snapshot);
          return this.api
            .renderPreviewHtml({
              title: w.title,
              code: w.code,
              blocks: w.blocks,
              meta: w.meta,
              current_version: w.current_version,
            })
            .pipe(
              map((html) => ({ doc, scrollTop, html })),
              catchError(() => of({ doc, scrollTop, html: manualToPreviewHtml(w) })),
            );
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ doc, scrollTop, html }) => this.applyPreviewHtml(doc, html, scrollTop));

    merge(interval(6_000), this.bump$)
      .pipe(debounceTime(2_000), takeUntilDestroyed(this.destroyRef))
      .subscribe(async () => {
        if (!this.store.dirty()) return;
        await this.store.save(false);
        const m = this.store.manual();
        if (m && !this.store.error()) this.clearLocalDraft(m.id);
      });

    this.persistDraft$
      .pipe(debounceTime(750), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.writeLocalDraftSnapshot());
  }

  @HostListener('document:visibilitychange')
  onVisibilityChange(): void {
    if (typeof document === 'undefined') return;
    if (document.visibilityState !== 'hidden' || !this.store.dirty()) return;
    void this.store.save(false).then(() => {
      const m = this.store.manual();
      if (m && !this.store.error()) this.clearLocalDraft(m.id);
    });
  }

  @HostListener('window:beforeunload', ['$event'])
  onBeforeUnload(event: BeforeUnloadEvent): void {
    if (!this.store.dirty()) return;
    const m = this.store.manual();
    if (m) {
      try {
        this.writeLocalDraftSnapshotNow(m);
      } catch {
        /* quota u otro */
      }
      const body = JSON.stringify({
        title: m.title,
        code: m.code,
        blocks: m.blocks,
        meta: m.meta,
        bump_version: false,
      });
      try {
        void fetch(`/api/v1/manuals/${m.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body,
          keepalive: true,
        });
      } catch {
        /* entorno sin fetch */
      }
    }
    event.preventDefault();
    event.returnValue = '';
  }

  private afterManualReady(): void {
    const m = this.store.manual();
    if (!m) return;
    const draft = this.readLocalDraft(m.id);
    if (draft && this.shouldOfferDraftRestore(draft, m)) {
      const snack = this.snack.open(
        'Hay un borrador local más reciente que la última versión guardada. ¿Recuperarlo?',
        'Recuperar',
        { duration: 14_000 },
      );
      snack.afterDismissed().subscribe((info) => {
        if (info.dismissedByAction) {
          this.store.restoreLocalDraft(draft.manual);
        }
        this.finalizeAfterLoad();
      });
      return;
    }
    this.finalizeAfterLoad();
  }

  private finalizeAfterLoad(): void {
    const m = this.store.manual();
    if (!m) return;
    if (needsOatiV2Migration(m)) {
      this.store.patchBlocks(normalizeManual(m).blocks);
    }
    const w = normalizeManual(this.store.manual()!);
    this.flowItems.set(extractFlowBlocks(w).map((b) => ({ ...b, data: { ...b.data } })));
    this.selectedStatic.set('oati_cover');
    this.selectedFlowId.set(null);
    this.activePanel.set('static');
    this.schedulePreviewWrite();
  }

  private draftStorageKey(id: string): string {
    return this.draftKeyPrefix + id;
  }

  private readLocalDraft(
    id: string,
  ): { v: number; savedAt: string; baseServerUpdatedAt: string | null; manual: Manual } | null {
    try {
      const raw = localStorage.getItem(this.draftStorageKey(id));
      if (!raw) return null;
      const o = JSON.parse(raw) as {
        v?: number;
        savedAt?: string;
        baseServerUpdatedAt?: string | null;
        manual?: Manual;
      };
      if (!o.manual || !o.savedAt) return null;
      return {
        v: typeof o.v === 'number' ? o.v : 1,
        savedAt: o.savedAt,
        baseServerUpdatedAt: o.baseServerUpdatedAt ?? null,
        manual: o.manual,
      };
    } catch {
      return null;
    }
  }

  private shouldOfferDraftRestore(
    draft: { savedAt: string; baseServerUpdatedAt: string | null; manual: Manual },
    serverManual: Manual,
  ): boolean {
    const base = draft.baseServerUpdatedAt ?? null;
    if (base !== (serverManual.updated_at ?? null)) return false;
    const saved = Date.parse(draft.savedAt);
    const srv = Date.parse(serverManual.updated_at ?? '1970-01-01T00:00:00.000Z');
    return Number.isFinite(saved) && saved > srv + 400;
  }

  private writeLocalDraftSnapshot(): void {
    const m = this.store.manual();
    if (!m || !this.store.dirty()) return;
    this.writeLocalDraftSnapshotNow(m);
  }

  private writeLocalDraftSnapshotNow(m: Manual): void {
    const payload = {
      v: 1 as const,
      savedAt: new Date().toISOString(),
      baseServerUpdatedAt: m.updated_at ?? null,
      manual: {
        ...m,
        blocks: m.blocks.map((b) => ({ ...b, data: { ...b.data } })),
        meta: { ...m.meta },
      },
    };
    localStorage.setItem(this.draftStorageKey(m.id), JSON.stringify(payload));
  }

  private clearLocalDraft(id: string): void {
    try {
      localStorage.removeItem(this.draftStorageKey(id));
    } catch {
      /* */
    }
  }

  private schedulePersistLocalDraft(): void {
    if (!this.store.dirty()) return;
    this.persistDraft$.next();
  }

  selectStatic(type: OatiBlockType): void {
    this.activePanel.set('static');
    this.selectedStatic.set(type);
    this.selectedFlowId.set(null);
  }

  selectFlow(id: string): void {
    this.activePanel.set('flow');
    this.selectedFlowId.set(id);
  }

  onManualTitleChange(title: string): void {
    this.store.patchManualMeta({ title });
    this.schedulePersistLocalDraft();
    this.bump$.next();
    this.schedulePreviewWrite();
  }

  onManualCodeChange(code: string): void {
    this.store.patchManualMeta({ code });
    this.schedulePersistLocalDraft();
    this.bump$.next();
    this.schedulePreviewWrite();
  }

  coverField(key: string): string {
    const raw = this.store.manual();
    if (!raw) return '';
    const m = normalizeManual(raw);
    const d = m.blocks.find((b) => b.type === 'oati_cover')?.data ?? {};
    return String(d[key] ?? '');
  }

  /** Escala del escudo en portada (50–150 %), para PDF/Word y vista previa. */
  crestScalePercent(): number {
    const raw = this.store.manual();
    if (!raw) return 100;
    const d = normalizeManual(raw).blocks.find((b) => b.type === 'oati_cover')?.data ?? {};
    const v = Number(d['crestScalePercent']);
    if (!Number.isFinite(v)) return 100;
    return Math.max(50, Math.min(150, Math.round(v)));
  }

  hasCoverCrestUpload(): boolean {
    const raw = this.store.manual();
    if (!raw) return false;
    const v = normalizeManual(raw).blocks.find((b) => b.type === 'oati_cover')?.data?.['crestData'];
    return typeof v === 'string' && v.length > 0;
  }

  hasCoverLogoUdUpload(): boolean {
    const raw = this.store.manual();
    if (!raw) return false;
    const v = normalizeManual(raw).blocks.find((b) => b.type === 'oati_cover')?.data?.['logoUdData'];
    return typeof v === 'string' && v.length > 0;
  }

  hasCoverLogoOatiUpload(): boolean {
    const raw = this.store.manual();
    if (!raw) return false;
    const v = normalizeManual(raw).blocks.find((b) => b.type === 'oati_cover')?.data?.['logoOatiData'];
    return typeof v === 'string' && v.length > 0;
  }

  onCoverLogoUdFile(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file?.type.startsWith('image/')) {
      input.value = '';
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      this.patchCover({
        logoUdData: String(reader.result ?? ''),
        logoUdUrl: '',
      });
      input.value = '';
    };
    reader.readAsDataURL(file);
  }

  onCoverLogoOatiFile(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file?.type.startsWith('image/')) {
      input.value = '';
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      this.patchCover({
        logoOatiData: String(reader.result ?? ''),
        logoOatiUrl: '',
      });
      input.value = '';
    };
    reader.readAsDataURL(file);
  }

  clearCoverLogoUdUpload(): void {
    this.patchCover({ logoUdData: '' });
  }

  clearCoverLogoOatiUpload(): void {
    this.patchCover({ logoOatiData: '' });
  }

  onCoverCrestFile(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file?.type.startsWith('image/')) {
      input.value = '';
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      this.patchCover({
        crestData: String(reader.result ?? ''),
        crestUrl: '',
      });
      input.value = '';
    };
    reader.readAsDataURL(file);
  }

  clearCoverCrestUpload(): void {
    this.patchCover({ crestData: '' });
  }

  sectionField(key: string): string {
    const manual = this.store.manual();
    if (!manual) return '';
    const m = normalizeManual(manual);
    const t = this.selectedStatic();
    const d = m.blocks.find((b) => b.type === t)?.data ?? {};
    const val = String(d[key] ?? '');
    if (key === 'text') return stripHtmlToPlain(val);
    return val;
  }

  stepField(b: ManualBlock, key: string): string {
    const raw = String(b.data[key] ?? '');
    if (key === 'description') return stripHtmlToPlain(raw);
    return raw;
  }

  noteField(b: ManualBlock): string {
    return stripHtmlToPlain(String(b.data['body'] ?? ''));
  }

  sectionImageScalePercent(): number {
    return imageScalePercent(this.activeSectionData());
  }

  stepImageScalePercent(b: ManualBlock): number {
    return imageScalePercent(b.data);
  }

  hasSectionUploadedImage(): boolean {
    const v = this.activeSectionData()['imageData'];
    return typeof v === 'string' && v.length > 0;
  }

  hasStepUploadedImage(b: ManualBlock): boolean {
    const v = b.data['imageData'];
    return typeof v === 'string' && v.length > 0;
  }

  onSectionImageFile(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file?.type.startsWith('image/')) {
      input.value = '';
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      this.patchSection(this.selectedStatic(), {
        imageData: String(reader.result ?? ''),
        imageSrc: '',
      });
      input.value = '';
    };
    reader.readAsDataURL(file);
  }

  onStepImageFile(ev: Event, blockId: string): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file?.type.startsWith('image/')) {
      input.value = '';
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      this.patchFlow(blockId, {
        imageData: String(reader.result ?? ''),
        imageSrc: '',
      });
      input.value = '';
    };
    reader.readAsDataURL(file);
  }

  clearSectionUploadedImage(): void {
    this.patchSection(this.selectedStatic(), { imageData: '' });
  }

  clearStepUploadedImage(blockId: string): void {
    this.patchFlow(blockId, { imageData: '' });
  }

  private activeSectionData(): Record<string, unknown> {
    const manual = this.store.manual();
    if (!manual) return {};
    const m = normalizeManual(manual);
    return m.blocks.find((b) => b.type === this.selectedStatic())?.data ?? {};
  }

  patchCover(patch: Record<string, unknown>): void {
    const m = normalizeManual(this.store.manual()!);
    const staticBlocks = extractStaticBlocks(m).map((b) =>
      b.type === 'oati_cover' ? { ...b, data: { ...b.data, ...patch } } : b,
    );
    this.store.patchBlocks(mergeFlowItems(staticBlocks, this.flowItems()));
    this.schedulePersistLocalDraft();
    this.bump$.next();
    this.schedulePreviewWrite();
  }

  patchSection(type: OatiBlockType, patch: Record<string, unknown>): void {
    const m = normalizeManual(this.store.manual()!);
    const staticBlocks = extractStaticBlocks(m).map((b) =>
      b.type === type ? { ...b, data: { ...b.data, ...patch } } : b,
    );
    this.store.patchBlocks(mergeFlowItems(staticBlocks, this.flowItems()));
    this.schedulePersistLocalDraft();
    this.bump$.next();
    this.schedulePreviewWrite();
  }

  patchFlow(id: string, patch: Record<string, unknown>): void {
    const next = this.flowItems().map((b) =>
      b.id === id ? { ...b, data: { ...b.data, ...patch } } : b,
    );
    this.flowItems.set(next);
    this.syncFlowToStore();
  }

  private syncFlowToStore(): void {
    const m = normalizeManual(this.store.manual()!);
    const staticBlocks = extractStaticBlocks(m);
    this.store.patchBlocks(mergeFlowItems(staticBlocks, this.flowItems()));
    this.schedulePersistLocalDraft();
    this.bump$.next();
    this.schedulePreviewWrite();
  }

  flowLabel(b: ManualBlock): string {
    if (b.type === 'oati_step') return String(b.data['title'] ?? 'Paso');
    return 'Nota';
  }

  trackFlow(_: number, b: ManualBlock): string {
    return b.id;
  }

  fabricate(kind: 'oati_step' | 'oati_note'): ManualBlock {
    if (kind === 'oati_step') {
      return {
        id: crypto.randomUUID(),
        type: 'oati_step',
        order: 0,
        data: {
          title: 'Título del paso',
          description: '',
          imageSrc: '',
          imageData: '',
          imageCaption: '',
          imageScalePercent: 100,
        },
      };
    }
    return {
      id: crypto.randomUUID(),
      type: 'oati_note',
      order: 0,
      data: { body: 'Texto de la nota.' },
    };
  }

  drop(event: CdkDragDrop<ManualBlock[] | { kind: 'oati_step' | 'oati_note' }[]>): void {
    if (event.previousContainer.id === 'palette') {
      const kind = (event.item.data as { kind: 'oati_step' | 'oati_note' }).kind;
      const nb = this.fabricate(kind);
      const data = [...this.flowItems()];
      data.splice(event.currentIndex, 0, nb);
      this.flowItems.set(data);
      this.syncFlowToStore();
      this.selectFlow(nb.id);
      return;
    }
    if (event.previousContainer === event.container) {
      const data = [...this.flowItems()];
      moveItemInArray(data, event.previousIndex, event.currentIndex);
      this.flowItems.set(data);
      this.syncFlowToStore();
    }
  }

  removeFlow(id: string): void {
    this.flowItems.set(this.flowItems().filter((b) => b.id !== id));
    if (this.selectedFlowId() === id) this.selectedFlowId.set(null);
    this.syncFlowToStore();
  }

  save(bump: boolean): void {
    void this.store.save(bump).then(() => {
      if (this.store.error()) {
        this.snack.open(this.store.error() ?? 'Error', 'Cerrar', { duration: 4500 });
        return;
      }
      const m = this.store.manual();
      if (m) this.clearLocalDraft(m.id);
      this.snack.open(bump ? 'Versión registrada' : 'Cambios guardados', 'OK', { duration: 2500 });
    });
  }

  async exportDocx(): Promise<void> {
    let manual = this.store.manual();
    if (!manual) return;
    if (this.store.dirty()) {
      await this.store.save(false);
      manual = this.store.manual();
      if (!manual || this.store.error()) {
        this.snack.open(this.store.error() ?? 'Guarde antes de exportar.', 'Cerrar', { duration: 4500 });
        return;
      }
      this.clearLocalDraft(manual.id);
    }
    const blob = await this.store.exportDocx();
    if (!blob) {
      this.snack.open(this.store.error() ?? 'Exportación Word no disponible', 'Cerrar', { duration: 3500 });
      return;
    }
    this.download(blob, `${manual.code}-v${manual.current_version}.docx`);
  }

  private schedulePreviewWrite(): void {
    if (this.previewTimer) clearTimeout(this.previewTimer);
    this.previewTimer = setTimeout(() => this.writePreview(), 600);
  }

  private writePreview(): void {
    const iframe = this.previewFrame()?.nativeElement;
    const m = this.store.manual();
    if (!iframe?.contentDocument || !m) return;
    const doc = iframe.contentDocument;
    let top = 0;
    try {
      top = doc.documentElement?.scrollTop ?? doc.body?.scrollTop ?? 0;
    } catch {
      /* iframe sin acceso al scroll */
    }
    const snapshot: Manual = {
      ...m,
      blocks: m.blocks.map((b) => ({ ...b, data: { ...b.data } })),
      meta: { ...m.meta },
    };
    this.preview$.next({ doc, scrollTop: top, snapshot });
  }

  private applyPreviewHtml(doc: Document, html: string, scrollTop: number): void {
    doc.open();
    doc.write(html);
    doc.close();
    requestAnimationFrame(() => {
      try {
        doc.documentElement.scrollTop = scrollTop;
        doc.body.scrollTop = scrollTop;
      } catch {
        /* ignorar */
      }
    });
  }

  private download(blob: Blob, name: string): void {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  }
}
