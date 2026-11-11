import { Component } from '@angular/core';
import { FormBuilder, Validators } from '@angular/forms';
import { MatLegacySnackBar as MatSnackBar } from '@angular/material/legacy-snack-bar';

export type DefaultView = 'issues' | 'board';

export interface Preferences {
  emailOnNew: boolean;
  compactTable: boolean;
  defaultView: DefaultView;
  dailyCapacity: number;
}

export const DEFAULT_PREFERENCES: Preferences = {
  emailOnNew: true,
  compactTable: false,
  defaultView: 'issues',
  dailyCapacity: 6,
};

@Component({
  selector: 'app-settings',
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
})
export class SettingsComponent {
  saved: Preferences = { ...DEFAULT_PREFERENCES };

  readonly form = this.fb.nonNullable.group({
    emailOnNew: [this.saved.emailOnNew],
    compactTable: [this.saved.compactTable],
    defaultView: [this.saved.defaultView],
    dailyCapacity: [this.saved.dailyCapacity, [Validators.required, Validators.min(1), Validators.max(12)]],
  });

  constructor(private readonly fb: FormBuilder, private readonly snackBar: MatSnackBar) {}

  save(): void {
    if (this.form.invalid) {
      return;
    }
    const previous = this.saved;
    this.saved = this.form.getRawValue();
    this.form.markAsPristine();
    this.snackBar
      .open('Settings saved', 'Undo', { duration: 5000 })
      .onAction()
      .subscribe(() => {
        this.saved = previous;
        this.form.reset(previous);
      });
  }
}
