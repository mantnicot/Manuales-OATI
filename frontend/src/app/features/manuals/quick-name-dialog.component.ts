import { Component, inject } from '@angular/core';

import { FormsModule } from '@angular/forms';

import { MatButtonModule } from '@angular/material/button';

import {

  MAT_DIALOG_DATA,

  MatDialogActions,

  MatDialogClose,

  MatDialogContent,

  MatDialogRef,

  MatDialogTitle,

} from '@angular/material/dialog';

import { MatFormFieldModule } from '@angular/material/form-field';

import { MatInputModule } from '@angular/material/input';



export interface QuickNameDialogData {

  title: string;

  label: string;

  value?: string;

}



@Component({

  selector: 'app-quick-name-dialog',

  standalone: true,

  imports: [

    FormsModule,

    MatDialogTitle,

    MatDialogContent,

    MatDialogActions,

    MatDialogClose,

    MatButtonModule,

    MatFormFieldModule,

    MatInputModule,

  ],

  template: `

    <h2 mat-dialog-title>{{ data.title }}</h2>

    <mat-dialog-content class="!pt-2">

      <mat-form-field appearance="outline" class="w-full">

        <mat-label>{{ data.label }}</mat-label>

        <input matInput [(ngModel)]="value" (keydown.enter)="submit()" autofocus />

      </mat-form-field>

    </mat-dialog-content>

    <mat-dialog-actions align="end">

      <button mat-button mat-dialog-close>Cancelar</button>

      <button mat-flat-button color="primary" (click)="submit()" [disabled]="!value.trim()">Aceptar</button>

    </mat-dialog-actions>

  `,

})

export class QuickNameDialogComponent {

  readonly data = inject<QuickNameDialogData>(MAT_DIALOG_DATA);

  private readonly ref = inject(MatDialogRef<QuickNameDialogComponent, string | undefined>);



  value = this.data.value ?? '';



  submit(): void {

    const v = this.value.trim();

    if (!v) return;

    this.ref.close(v);

  }

}

