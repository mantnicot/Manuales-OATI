import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';

import { ManualApiService } from './manual-api.service';

/** Chrome/Edge a veces devuelven el Blob sin tipo; sin `application/pdf` el visor embebido queda en blanco. */
export function ensurePdfBlob(blob: Blob): Blob {
  const t = (blob.type || '').toLowerCase();
  if (t.includes('pdf')) return blob;
  return new Blob([blob], { type: 'application/pdf' });
}

/** Lee mensaje de error típico de FastAPI desde un cuerpo JSON (blob). */
export async function readApiErrorFromBlob(blob: Blob | null, fallback: string): Promise<string> {
  if (!blob) return fallback;
  try {
    const t = await blob.text();
    const j = JSON.parse(t) as { detail?: unknown };
    const d = j.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) {
      const parts = d
        .map((x) => (typeof x === 'object' && x && 'msg' in x ? String((x as { msg: string }).msg) : ''))
        .filter(Boolean);
      if (parts.length) return parts.join('; ');
    }
    return fallback;
  } catch {
    return fallback;
  }
}

@Injectable({ providedIn: 'root' })
export class PdfBrowserService {
  private readonly http = inject(HttpClient);
  private readonly api = inject(ManualApiService);
  private readonly snack = inject(MatSnackBar);

  /** Abre una pestaña con el PDF recibido; revoca la URL al cabo de un tiempo. */
  openBlobPdfInNewTab(blob: Blob): boolean {
    if (blob.size < 32) {
      this.snack.open('El archivo PDF está vacío.', 'Cerrar', { duration: 6000 });
      return false;
    }
    const url = URL.createObjectURL(ensurePdfBlob(blob));
    const w = window.open(url, '_blank', 'noopener,noreferrer');
    if (!w) {
      this.snack.open(
        'El navegador bloqueó la ventana emergente. Permita ventanas para este sitio e intente de nuevo.',
        'Cerrar',
        { duration: 9000 },
      );
      URL.revokeObjectURL(url);
      return false;
    }
    window.setTimeout(() => URL.revokeObjectURL(url), 180_000);
    return true;
  }

  /** PDF generado desde plantilla (manual / guía rápida). */
  openGeneratedPdfInNewTab(manualId: string): void {
    this.http
      .get(this.api.exportPdfUrl(manualId, { inline: true }), { responseType: 'blob', observe: 'response' })
      .subscribe({
        next: async (res: HttpResponse<Blob>) => {
          if (res.status >= 400 || !res.body) {
            this.snack.open(await readApiErrorFromBlob(res.body, `Error ${res.status} al generar el PDF.`), 'Cerrar', {
              duration: 10000,
            });
            return;
          }
          const ct = (res.headers.get('content-type') || '').toLowerCase();
          if (ct.includes('application/json')) {
            this.snack.open(await readApiErrorFromBlob(res.body, 'El servidor devolvió JSON en lugar del PDF.'), 'Cerrar', {
              duration: 10000,
            });
            return;
          }
          this.openBlobPdfInNewTab(res.body);
        },
        error: async (err: HttpErrorResponse) => {
          if (err.error instanceof Blob) {
            this.snack.open(
              await readApiErrorFromBlob(err.error, `No se pudo obtener el PDF (${err.status}).`),
              'Cerrar',
              { duration: 10000 },
            );
            return;
          }
          this.snack.open(
            `No se pudo conectar con el API para el PDF (${err.status}). ¿Está el backend en ejecución y el proxy activo?`,
            'Cerrar',
            { duration: 10000 },
          );
        },
      });
  }

  /** PDF almacenado (upload). */
  openStoredPdfInNewTab(manualId: string): void {
    const url = `${this.api.pdfFileUrl(manualId)}?inline=1`;
    this.http.get(url, { responseType: 'blob', observe: 'response' }).subscribe({
      next: async (res: HttpResponse<Blob>) => {
        if (res.status >= 400 || !res.body) {
          this.snack.open(await readApiErrorFromBlob(res.body, `Error ${res.status} abriendo el PDF.`), 'Cerrar', {
            duration: 8000,
          });
          return;
        }
        this.openBlobPdfInNewTab(res.body);
      },
      error: async (err: HttpErrorResponse) => {
        if (err.error instanceof Blob) {
          this.snack.open(await readApiErrorFromBlob(err.error, 'No se pudo abrir el PDF almacenado.'), 'Cerrar', {
            duration: 9000,
          });
          return;
        }
        this.snack.open('Error de red al abrir el PDF. Compruebe el API.', 'Cerrar', { duration: 8000 });
      },
    });
  }

  /** Vista previa HTML del servidor (misma que incluye la barra con enlace a PDF). */
  openHtmlPreviewInNewTab(manualId: string): void {
    this.http.get(this.api.previewUrl(manualId), { responseType: 'text', observe: 'response' }).subscribe({
      next: (res: HttpResponse<string>) => {
        if (res.status >= 400 || res.body == null) {
          this.snack.open(`No se pudo cargar la vista previa (${res.status}).`, 'Cerrar', { duration: 8000 });
          return;
        }
        const origin = window.location.origin;
        // Desde blob: los href relativos /api fallan; forzar mismo origen que el front (proxy).
        const html = res.body
          .replace(/href="\/api\/v1\//g, `href="${origin}/api/v1/`)
          .replace(/src="\/api\/v1\//g, `src="${origin}/api/v1/`);
        const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const w = window.open(url, '_blank', 'noopener,noreferrer');
        if (!w) {
          this.snack.open(
            'El navegador bloqueó la ventana emergente al abrir la vista previa HTML.',
            'Cerrar',
            { duration: 8000 },
          );
          URL.revokeObjectURL(url);
          return;
        }
        window.setTimeout(() => URL.revokeObjectURL(url), 300_000);
      },
      error: () =>
        this.snack.open(
          'Error al cargar la vista previa. Compruebe que el backend esté en ejecución.',
          'Cerrar',
          { duration: 8000 },
        ),
    });
  }
}
