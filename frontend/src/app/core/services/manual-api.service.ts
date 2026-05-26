import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

import { Manual } from '../models/manual.models';

export interface RenderHtmlPayload {
  title: string;
  code: string;
  blocks: Manual['blocks'];
  meta: Record<string, unknown>;
  current_version: number;
}

@Injectable({ providedIn: 'root' })
export class ManualApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1';

  list(params?: { q?: string; status?: string }): Observable<{ total: number; items: Manual[] }> {
    return this.http.get<{ total: number; items: Manual[] }>(`${this.base}/manuals`, { params: params as never });
  }

  get(id: string): Observable<Manual> {
    return this.http.get<Manual>(`${this.base}/manuals/${id}`);
  }

  create(body: {
    title: string;
    code: string;
    use_official_template?: boolean;
    document_kind?: string | null;
    system_id?: string | null;
    folder_id?: string | null;
  }): Observable<Manual> {
    return this.http.post<Manual>(`${this.base}/manuals`, body);
  }

  /** Sube un .pdf almacenado; el registro aparece en la biblioteca (arrastrable como el resto). */
  uploadPdf(
    file: File,
    opts?: { title?: string; code?: string; system_id?: string | null; folder_id?: string | null },
  ): Observable<Manual> {
    const fd = new FormData();
    fd.append('file', file, file.name);
    if (opts?.title) fd.append('title', opts.title);
    if (opts?.code) fd.append('code', opts.code);
    if (opts?.system_id) fd.append('system_id', opts.system_id);
    if (opts?.folder_id) fd.append('folder_id', opts.folder_id);
    return this.http.post<Manual>(`${this.base}/manuals/actions/upload-pdf`, fd);
  }

  pdfFileUrl(id: string): string {
    return `${this.base}/manuals/${id}/pdf-file`;
  }

  /** PDF generado desde el HTML del manual o guía rápida (no confundir con pdf-file de solo-PDF). */
  exportPdfUrl(id: string, opts?: { inline?: boolean }): string {
    const q = opts?.inline ? '?inline=1' : '';
    return `${this.base}/manuals/${id}/export.pdf${q}`;
  }

  update(
    id: string,
    body: Partial<Pick<Manual, 'title' | 'code' | 'status' | 'blocks' | 'meta' | 'system_id' | 'folder_id'>> & {
      bump_version?: boolean;
    },
  ): Observable<Manual> {
    return this.http.patch<Manual>(`${this.base}/manuals/${id}`, body);
  }

  duplicate(id: string, newCode: string): Observable<Manual> {
    return this.http.post<Manual>(`${this.base}/manuals/${id}/duplicate`, {}, {
      params: { new_code: newCode },
    });
  }

  archive(id: string): Observable<void> {
    return this.http
      .delete(`${this.base}/manuals/${id}`, {
        observe: 'response',
        responseType: 'text',
      })
      .pipe(
        map((res: HttpResponse<string>) => {
          if (res.status === 204) {
            return undefined;
          }
          if (res.status === 200) {
            return undefined;
          }
          throw new HttpErrorResponse({
            status: res.status,
            statusText: res.statusText,
            url: res.url ?? undefined,
            error: res.body ?? undefined,
          });
        }),
      );
  }

  /** HTML idéntico al usado en export PDF/Word (servidor). */
  renderPreviewHtml(body: RenderHtmlPayload): Observable<string> {
    return this.http.post(`${this.base}/manuals/actions/render-html`, body, { responseType: 'text' });
  }

  previewUrl(id: string): string {
    return `${this.base}/manuals/${id}/preview`;
  }
}
