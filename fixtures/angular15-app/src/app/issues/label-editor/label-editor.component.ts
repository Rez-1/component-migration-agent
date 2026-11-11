import { COMMA, ENTER } from '@angular/cdk/keycodes';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatLegacyChipInputEvent as MatChipInputEvent } from '@angular/material/legacy-chips';

/** Edits an issue's labels: type a label and press Enter or comma to add it. */
@Component({
  selector: 'app-label-editor',
  template: `
    <mat-form-field class="labels-field">
      <mat-label>Labels</mat-label>
      <mat-chip-list #chipList aria-label="Issue labels">
        <mat-chip
          *ngFor="let label of labels"
          [selectable]="false"
          [removable]="true"
          (removed)="remove(label)"
        >
          {{ label }}
          <button matChipRemove [attr.aria-label]="'Remove ' + label">
            <mat-icon>cancel</mat-icon>
          </button>
        </mat-chip>
        <input
          placeholder="Add a label"
          [matChipInputFor]="chipList"
          [matChipInputSeparatorKeyCodes]="separatorKeys"
          [matChipInputAddOnBlur]="true"
          (matChipInputTokenEnd)="add($event)"
        />
      </mat-chip-list>
    </mat-form-field>
  `,
  styles: [
    `
      .labels-field {
        width: 100%;
      }
    `,
  ],
})
export class LabelEditorComponent {
  @Input() labels: string[] = [];
  @Output() labelsChange = new EventEmitter<string[]>();

  readonly separatorKeys = [ENTER, COMMA] as const;

  add(event: MatChipInputEvent): void {
    const label = event.value.trim().toLowerCase();
    if (label && !this.labels.includes(label)) {
      this.labels = [...this.labels, label];
      this.labelsChange.emit(this.labels);
    }
    event.chipInput?.clear();
  }

  remove(label: string): void {
    this.labels = this.labels.filter((l) => l !== label);
    this.labelsChange.emit(this.labels);
  }
}
