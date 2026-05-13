import { HttpClient } from '@angular/common/http';
import { patchState, signalStore, withMethods, withState } from '@ngrx/signals';
import { inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { Manual } from '../../core/models/manual.models';
import { ManualApiService } from '../../core/services/manual-api.service';

type EditorState = {
  manual: Manual | null;
  error: string | null;
  saving: boolean;
  dirty: boolean;
};

const initialState: EditorState = {
  manual: null,
  error: null,
  saving: false,
  dirty: false,
};

export const ManualEditorStore = signalStore(
  withState(initialState),
  withMethods((store) => {
    const api = inject(ManualApiService);
    const http = inject(HttpClient);
    const base = '/api/v1';

    return {
      reset() {
        patchState(store, initialState);
      },
      setManual(manual: Manual) {
        patchState(store, { manual, dirty: false, error: null });
      },
      patchBlocks(blocks: Manual['blocks']) {
        const m = store.manual();
        if (!m) return;
        const clone = blocks.map((b) => ({ ...b, data: { ...b.data } }));
        patchState(store, { manual: { ...m, blocks: clone }, dirty: true });
      },
      patchManualMeta(fields: Partial<Pick<Manual, 'title' | 'code'>>) {
        const m = store.manual();
        if (!m) return;
        patchState(store, { manual: { ...m, ...fields }, dirty: true });
      },
      markClean() {
        patchState(store, { dirty: false });
      },
      /** Restaura un borrador local (p. ej. tras cerrar la pestaña sin guardar). */
      restoreLocalDraft(manual: Manual) {
        const m = {
          ...manual,
          blocks: manual.blocks.map((b) => ({ ...b, data: { ...b.data } })),
          meta: { ...manual.meta },
        };
        patchState(store, { manual: m, dirty: true, error: null });
      },
      async load(id: string) {
        patchState(store, { error: null });
        try {
          const manual = await firstValueFrom(api.get(id));
          patchState(store, { manual, dirty: false });
        } catch {
          patchState(store, { error: 'No se pudo cargar el manual.', manual: null });
        }
      },
      async save(bumpVersion: boolean) {
        const manual = store.manual();
        if (!manual) return;
        patchState(store, { saving: true, error: null });
        try {
          const updated = await firstValueFrom(
            api.update(manual.id, { ...manual, bump_version: bumpVersion }),
          );
          patchState(store, { manual: updated, saving: false, dirty: false });
        } catch {
          patchState(store, { saving: false, error: 'Error al guardar cambios.' });
        }
      },
      async exportDocx(): Promise<Blob | null> {
        const manual = store.manual();
        if (!manual) return null;
        patchState(store, { error: null });
        try {
          const resp = await firstValueFrom(
            http.get(`${base}/manuals/${manual.id}/export.docx`, {
              observe: 'response',
              responseType: 'blob',
            }),
          );
          const ct = resp.headers.get('content-type') ?? '';
          if (resp.status >= 400 || ct.includes('application/json')) {
            let detail = 'No se pudo exportar a Word.';
            if (resp.body) {
              try {
                const txt = await resp.body.text();
                const parsed = JSON.parse(txt) as { detail?: string };
                if (parsed.detail) detail = parsed.detail;
              } catch {
                /* cuerpo no JSON */
              }
            }
            patchState(store, { error: detail });
            return null;
          }
          if ((resp.body?.size ?? 0) < 200) {
            patchState(store, {
              error:
                'El archivo Word recibido parece vacío. Guarde el manual y compruebe que tenga bloques.',
            });
            return null;
          }
          return resp.body;
        } catch {
          patchState(store, { error: 'No se pudo exportar Word.' });
          return null;
        }
      },
    };
  }),
);
