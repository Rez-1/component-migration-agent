import { CommonModule } from '@angular/common';
import { NgModule } from '@angular/core';
import { ReactiveFormsModule } from '@angular/forms';

import { ConfirmButtonComponent } from './confirm-button/confirm-button.component';
import { MaterialModule } from './material.module';
import { SearchBoxComponent } from './search-box/search-box.component';

@NgModule({
  declarations: [ConfirmButtonComponent, SearchBoxComponent],
  imports: [CommonModule, ReactiveFormsModule, MaterialModule],
  exports: [CommonModule, ReactiveFormsModule, MaterialModule, ConfirmButtonComponent, SearchBoxComponent],
})
export class SharedModule {}
