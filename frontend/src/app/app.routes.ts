import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', loadComponent: () => import('./features/manuals/manual-list.component').then((m) => m.ManualListComponent) },
  {
    path: 'manual/:id',
    loadComponent: () => import('./features/editor/manual-editor.component').then((m) => m.ManualEditorComponent),
  },
  { path: '**', redirectTo: '' },
];
