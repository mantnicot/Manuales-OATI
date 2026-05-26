import { NgFor, NgIf } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, ElementRef, inject, ViewChild } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import {
  CdkDrag,
  CdkDragDrop,
  CdkDragHandle,
  DragDropModule,
  moveItemInArray,
  transferArrayItem,
} from '@angular/cdk/drag-drop';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { forkJoin, of } from 'rxjs';
import { catchError, filter, mergeMap } from 'rxjs/operators';

import { ConfirmDialogComponent } from './confirm-dialog.component';
import { QuickNameDialogComponent } from './quick-name-dialog.component';
import { isPdfStorageManual, isQuickGuideManual, Manual } from '../../core/models/manual.models';
import { LibraryApiService, LibraryFolder, LibrarySystem } from '../../core/services/library-api.service';
import { ManualApiService } from '../../core/services/manual-api.service';
import { PdfBrowserService } from '../../core/services/pdf-browser.service';

@Component({
  selector: 'app-manual-list',
  standalone: true,
  imports: [
    NgFor,
    NgIf,
    RouterLink,
    DragDropModule,
    CdkDrag,
    CdkDragHandle,
    MatToolbarModule,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatExpansionModule,
    MatDialogModule,
    MatTooltipModule,
  ],
  templateUrl: './manual-list.component.html',
})
export class ManualListComponent {
  private readonly api = inject(ManualApiService);
  private readonly pdfBrowser = inject(PdfBrowserService);
  private readonly library = inject(LibraryApiService);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly snack = inject(MatSnackBar);

  @ViewChild('pdfFileInput') pdfFileInput?: ElementRef<HTMLInputElement>;

  readonly isPdfManual = isPdfStorageManual;
  readonly isQuickGuide = isQuickGuideManual;

  /** Editor OATI o guía rápida según el tipo de documento. */
  editorPath(m: Manual): string[] {
    return this.isQuickGuide(m) ? ['/quick-guide', m.id] : ['/manual', m.id];
  }

  manuals: Manual[] = [];
  systems: LibrarySystem[] = [];
  folders: LibraryFolder[] = [];
  busy = false;
  /** Texto bajo el spinner del overlay de bloqueo. */
  overlayMessage = '';
  error: string | null = null;

  binUnassigned: Manual[] = [];
  binFolderMap = new Map<string, Manual[]>();
  binSystemRootMap = new Map<string, Manual[]>();
  dropListIds: string[] = [];

  constructor() {
    this.reloadAll();
  }

  foldersOf(systemId: string): LibraryFolder[] {
    return this.folders.filter((f) => f.system_id === systemId);
  }

  reloadAll(): void {
    this.busy = true;
    this.overlayMessage = 'Cargando biblioteca…';
    this.error = null;
    forkJoin({
      mans: this.api.list().pipe(catchError(() => of({ total: 0, items: [] as Manual[] }))),
      lib: this.library.snapshot().pipe(catchError(() => of({ systems: [], folders: [] }))),
    }).subscribe({
      next: ({ mans, lib }) => {
        this.manuals = mans.items;
        this.systems = lib.systems;
        this.folders = lib.folders;
        this.repartitionBins();
        this.busy = false;
        this.overlayMessage = '';
      },
      error: () => {
        this.error =
          'No se pudo cargar la biblioteca. Compruebe que el backend esté en ejecución y el proxy de Angular apunte al API.';
        this.busy = false;
        this.overlayMessage = '';
        this.snack.open(this.error, 'Cerrar', { duration: 8000 });
      },
    });
  }

  repartitionBins(): void {
    this.binUnassigned = [];
    this.binFolderMap = new Map();
    this.binSystemRootMap = new Map();
    for (const f of this.folders) {
      this.binFolderMap.set(f.id, []);
    }
    for (const s of this.systems) {
      this.binSystemRootMap.set(s.id, []);
    }
    for (const m of this.manuals) {
      if (m.folder_id && this.binFolderMap.has(m.folder_id)) {
        this.binFolderMap.get(m.folder_id)!.push(m);
      } else if (m.system_id && this.binSystemRootMap.has(m.system_id) && !m.folder_id) {
        this.binSystemRootMap.get(m.system_id)!.push(m);
      } else {
        this.binUnassigned.push(m);
      }
    }
    this.dropListIds = [
      'bin-unassigned',
      ...this.systems.map((s) => `bin-sys-${s.id}`),
      ...this.folders.map((f) => `bin-fold-${f.id}`),
    ];
  }

  onDrop(
    event: CdkDragDrop<Manual[]>,
    kind: 'unassigned' | 'system' | 'folder',
    systemId?: string,
    folderId?: string,
  ): void {
    if (event.previousContainer === event.container) {
      moveItemInArray(event.container.data, event.previousIndex, event.currentIndex);
      return;
    }
    const manual = event.previousContainer.data[event.previousIndex];
    transferArrayItem(
      event.previousContainer.data,
      event.container.data,
      event.previousIndex,
      event.currentIndex,
    );
    let system_id: string | null = null;
    let folder_id: string | null = null;
    if (kind === 'folder' && folderId && systemId) {
      system_id = systemId;
      folder_id = folderId;
    } else if (kind === 'system' && systemId) {
      system_id = systemId;
      folder_id = null;
    }
    this.busy = true;
    this.overlayMessage = 'Guardando nueva ubicación…';
    this.api.update(manual.id, { system_id, folder_id }).subscribe({
      next: (upd) => {
        Object.assign(manual, upd);
        this.busy = false;
        this.overlayMessage = '';
        this.snack.open('Ubicación actualizada.', 'Cerrar', { duration: 3000 });
      },
      error: (err) => {
        this.busy = false;
        this.overlayMessage = '';
        const msg = this.httpErrorDetail(err, 'No se pudo mover el manual.');
        this.snack.open(msg, 'Cerrar', { duration: 6000 });
        this.reloadAll();
      },
    });
  }

  createQuickGuide(): void {
    this.busy = true;
    this.overlayMessage = 'Creando guía rápida…';
    this.error = null;
    const code = `GR-${Date.now().toString(36).toUpperCase()}`;
    this.api
      .create({
        title: 'Nueva guía rápida',
        code,
        use_official_template: false,
        document_kind: 'quick_guide',
      })
      .subscribe({
        next: (m) => {
          this.busy = false;
          this.overlayMessage = '';
          this.snack.open('Guía rápida creada. Abriendo editor…', 'Cerrar', { duration: 3000 });
          void this.router.navigate(['/quick-guide', m.id]);
        },
        error: (err) => {
          this.busy = false;
          this.overlayMessage = '';
          this.error = this.httpErrorDetail(err, 'No se pudo crear la guía rápida.');
          this.snack.open(this.error, 'Cerrar', { duration: 6000 });
        },
      });
  }

  createManual(): void {
    this.busy = true;
    this.overlayMessage = 'Creando manual…';
    this.error = null;
    const code = `MAN-${Date.now().toString(36).toUpperCase()}`;
    this.api.create({ title: 'Nuevo manual institucional', code, use_official_template: true }).subscribe({
      next: (m) => {
        this.busy = false;
        this.overlayMessage = '';
        this.snack.open('Manual creado. Abriendo editor…', 'Cerrar', { duration: 3000 });
        void this.router.navigate(['/manual', m.id]);
      },
      error: (err) => {
        this.busy = false;
        this.overlayMessage = '';
        this.error = this.httpErrorDetail(err, 'No se pudo crear el manual.');
        this.snack.open(this.error, 'Cerrar', { duration: 6000 });
      },
    });
  }

  /** Ojito: HTML en nueva pestaña (manuales/guías) o PDF vía blob (archivos .pdf subidos). */
  openEyePreview(m: Manual, ev: Event): void {
    ev.preventDefault();
    ev.stopPropagation();
    if (this.isPdfManual(m)) {
      this.pdfBrowser.openStoredPdfInNewTab(m.id);
    } else {
      this.pdfBrowser.openHtmlPreviewInNewTab(m.id);
    }
  }

  pdfDownloadUrl(m: Manual): string {
    if (isPdfStorageManual(m)) return this.api.pdfFileUrl(m.id);
    return this.api.exportPdfUrl(m.id);
  }

  pickPdfFile(): void {
    this.pdfFileInput?.nativeElement.click();
  }

  onPdfFileInputChange(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const f = input.files?.[0];
    input.value = '';
    if (f) this.uploadPdfFile(f);
  }

  /** Sin sistema ni carpeta; luego puede arrastrarlo en la biblioteca. */
  uploadPdfFile(
    file: File,
    ctx?: { system_id?: string | null; folder_id?: string | null },
  ): void {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      this.error = 'Solo se admiten archivos .pdf.';
      return;
    }
    this.busy = true;
    this.overlayMessage = 'Subiendo PDF…';
    this.error = null;
    this.api
      .uploadPdf(file, {
        system_id: ctx?.system_id ?? undefined,
        folder_id: ctx?.folder_id ?? undefined,
      })
      .subscribe({
        next: () => {
          this.busy = false;
          this.overlayMessage = '';
          this.snack.open('PDF subido correctamente.', 'Cerrar', { duration: 4000 });
          this.reloadAll();
        },
        error: (err) => {
          this.busy = false;
          this.overlayMessage = '';
          this.error = this.httpErrorDetail(err, 'No se pudo subir el PDF.');
          this.snack.open(this.error, 'Cerrar', { duration: 7000 });
        },
      });
  }

  onPdfDragOver(e: DragEvent): void {
    e.preventDefault();
    e.stopPropagation();
  }

  onPdfDrop(
    e: DragEvent,
    ctx: 'unassigned' | 'system' | 'folder',
    systemId?: string,
    folderId?: string,
  ): void {
    e.preventDefault();
    e.stopPropagation();
    const f = e.dataTransfer?.files?.[0];
    if (!f || !f.name.toLowerCase().endsWith('.pdf')) return;
    if (ctx === 'unassigned') this.uploadPdfFile(f);
    else if (ctx === 'system' && systemId) this.uploadPdfFile(f, { system_id: systemId, folder_id: null });
    else if (ctx === 'folder' && folderId) this.uploadPdfFile(f, { folder_id: folderId });
  }

  addSystem(): void {
    this.dialog
      .open(QuickNameDialogComponent, {
        width: '380px',
        data: { title: 'Nuevo sistema', label: 'Nombre del sistema', value: '' },
      })
      .afterClosed()
      .subscribe((name) => {
        if (!name) return;
        this.library.createSystem(name).subscribe({
          next: () => this.reloadAll(),
          error: () => (this.error = 'No se pudo crear el sistema.'),
        });
      });
  }

  addFolder(s: LibrarySystem): void {
    this.dialog
      .open(QuickNameDialogComponent, {
        width: '380px',
        data: { title: 'Nueva carpeta', label: 'Nombre de la carpeta', value: '' },
      })
      .afterClosed()
      .subscribe((name) => {
        if (!name) return;
        this.library.createFolder(name, s.id).subscribe({
          next: () => this.reloadAll(),
          error: () => (this.error = 'No se pudo crear la carpeta.'),
        });
      });
  }

  renameSystem(s: LibrarySystem): void {
    this.dialog
      .open(QuickNameDialogComponent, {
        width: '380px',
        data: { title: 'Renombrar sistema', label: 'Nombre', value: s.name },
      })
      .afterClosed()
      .subscribe((name) => {
        if (!name || name === s.name) return;
        this.library.updateSystem(s.id, name).subscribe({
          next: () => this.reloadAll(),
          error: () => (this.error = 'No se pudo actualizar el sistema.'),
        });
      });
  }

  renameFolder(f: LibraryFolder): void {
    this.dialog
      .open(QuickNameDialogComponent, {
        width: '380px',
        data: { title: 'Renombrar carpeta', label: 'Nombre', value: f.name },
      })
      .afterClosed()
      .subscribe((name) => {
        if (!name || name === f.name) return;
        this.library.updateFolder(f.id, name).subscribe({
          next: () => this.reloadAll(),
          error: () => (this.error = 'No se pudo actualizar la carpeta.'),
        });
      });
  }

  deleteSystem(s: LibrarySystem): void {
    if (!confirm(`¿Eliminar el sistema «${s.name}» y sus carpetas? Los manuales quedarán sin clasificar.`)) return;
    this.library.deleteSystem(s.id).subscribe({
      next: () => this.reloadAll(),
      error: () => (this.error = 'No se pudo eliminar el sistema.'),
    });
  }

  deleteFolder(f: LibraryFolder): void {
    if (!confirm(`¿Eliminar la carpeta «${f.name}»? Los manuales pasarán a «sin carpeta» en el mismo sistema.`)) return;
    this.library.deleteFolder(f.id).subscribe({
      next: () => this.reloadAll(),
      error: () => (this.error = 'No se pudo eliminar la carpeta.'),
    });
  }

  renameManual(m: Manual): void {
    this.dialog
      .open(QuickNameDialogComponent, {
        width: '420px',
        data: { title: 'Renombrar manual', label: 'Nombre visible del manual', value: m.title },
      })
      .afterClosed()
      .subscribe((title) => {
        if (!title || title === m.title) return;
        this.api.update(m.id, { title }).subscribe({
          next: (upd) => {
            Object.assign(m, upd);
            this.repartitionBins();
          },
          error: () => (this.error = 'No se pudo renombrar el manual.'),
        });
      });
  }

  deleteManual(m: Manual): void {
    const extra = this.isPdfManual(m)
      ? 'También se borrará el archivo PDF en el servidor. Esta acción no se puede deshacer.'
      : 'El borrado es definitivo en la biblioteca. Esta acción no se puede deshacer.';
    this.dialog
      .open(ConfirmDialogComponent, {
        width: '440px',
        disableClose: true,
        data: {
          title: 'Eliminar manual',
          message: `¿Confirma eliminar «${m.title}»?\n\n${extra}`,
          confirmLabel: 'Eliminar',
          cancelLabel: 'Cancelar',
          confirmColor: 'warn' as const,
        },
      })
      .afterClosed()
      .pipe(
        filter((v): v is true => v === true),
        mergeMap(() => {
          this.busy = true;
          this.overlayMessage = 'Eliminando…';
          this.error = null;
          return this.api.archive(m.id);
        }),
      )
      .subscribe({
        next: () => {
          this.busy = false;
          this.overlayMessage = '';
          this.snack.open('Manual eliminado correctamente.', 'Cerrar', { duration: 4500 });
          this.reloadAll();
        },
        error: (err) => {
          this.busy = false;
          this.overlayMessage = '';
          const msg = this.httpErrorDetail(err, 'No se pudo eliminar el manual.');
          this.error = msg;
          this.snack.open(msg, 'Cerrar', { duration: 8000 });
        },
      });
  }

  private httpErrorDetail(err: unknown, fallback: string): string {
    if (err instanceof HttpErrorResponse) {
      const body = err.error;
      if (body && typeof body === 'object' && 'detail' in body) {
        const d = (body as { detail: unknown }).detail;
        if (typeof d === 'string') return d;
        if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg);
      }
      if (typeof body === 'string' && body) {
        try {
          const p = JSON.parse(body) as { detail?: string };
          if (p.detail) return p.detail;
        } catch {
          /* ignore */
        }
      }
      if (err.status === 0) {
        return 'Sin conexión con el servidor. Compruebe que la API esté en ejecución.';
      }
    }
    return fallback;
  }
}
