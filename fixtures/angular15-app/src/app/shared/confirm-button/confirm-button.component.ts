import { Component, EventEmitter, Input, Output } from '@angular/core';
import { ThemePalette } from '@angular/material/core';

/**
 * A button that asks for a second click before it acts: the first click arms it
 * and changes its label, the second emits `confirmed`. Leaving it disarms it.
 */
@Component({
  selector: 'app-confirm-button',
  templateUrl: './confirm-button.component.html',
  styleUrls: ['./confirm-button.component.scss'],
})
export class ConfirmButtonComponent {
  @Input() label = 'Delete';
  @Input() confirmLabel = 'Click again to confirm';
  @Input() icon?: string;
  @Input() color: ThemePalette = 'warn';
  @Output() confirmed = new EventEmitter<void>();

  armed = false;

  onClick(): void {
    if (this.armed) {
      this.armed = false;
      this.confirmed.emit();
    } else {
      this.armed = true;
    }
  }

  disarm(): void {
    this.armed = false;
  }
}
