import { Component, Inject } from '@angular/core';
import { FormBuilder, Validators } from '@angular/forms';
import {
  MAT_LEGACY_DIALOG_DATA as MAT_DIALOG_DATA,
  MatLegacyDialogRef as MatDialogRef,
} from '@angular/material/legacy-dialog';

import { IssueType, Member, NewIssue } from '../../data/issue';

export interface NewIssueDialogData {
  members: Member[];
}

@Component({
  selector: 'app-new-issue-dialog',
  templateUrl: './new-issue-dialog.component.html',
  styleUrls: ['./new-issue-dialog.component.scss'],
})
export class NewIssueDialogComponent {
  readonly types: IssueType[] = ['bug', 'feature', 'chore'];

  readonly form = this.fb.nonNullable.group({
    title: ['', [Validators.required, Validators.maxLength(120)]],
    type: ['bug' as IssueType],
    assignee: [null as string | null],
    priority: [3],
  });

  constructor(
    private readonly fb: FormBuilder,
    private readonly dialogRef: MatDialogRef<NewIssueDialogComponent, NewIssue>,
    @Inject(MAT_DIALOG_DATA) readonly data: NewIssueDialogData,
  ) {}

  priorityLabel(value: number): string {
    return ['Lowest', 'Low', 'Medium', 'High', 'Highest'][value - 1] ?? '';
  }

  create(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const { title, type, assignee, priority } = this.form.getRawValue();
    this.dialogRef.close({ title: title.trim(), type, assignee, priority });
  }
}
