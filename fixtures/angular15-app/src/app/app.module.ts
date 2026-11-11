import { NgModule } from '@angular/core';
import {
  MAT_LEGACY_FORM_FIELD_DEFAULT_OPTIONS as MAT_FORM_FIELD_DEFAULT_OPTIONS,
  MatLegacyFormFieldDefaultOptions as MatFormFieldDefaultOptions,
} from '@angular/material/legacy-form-field';
import { BrowserModule } from '@angular/platform-browser';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';

import { AppRoutingModule } from './app-routing.module';
import { AppComponent } from './app.component';
import { BoardComponent } from './board/board.component';
import { IssueDetailComponent } from './issues/issue-detail/issue-detail.component';
import { IssueFiltersComponent } from './issues/issue-filters/issue-filters.component';
import { IssueListComponent } from './issues/issue-list/issue-list.component';
import { LabelEditorComponent } from './issues/label-editor/label-editor.component';
import { NewIssueDialogComponent } from './issues/new-issue-dialog/new-issue-dialog.component';
import { SettingsComponent } from './settings/settings.component';
import { SharedModule } from './shared/shared.module';
import { TeamComponent } from './team/team.component';

/** Form fields across the app: the underlined look, labels float only when needed. */
export const FORM_FIELD_DEFAULTS: MatFormFieldDefaultOptions = {
  appearance: 'legacy',
  floatLabel: 'auto',
};

@NgModule({
  declarations: [
    AppComponent,
    BoardComponent,
    IssueDetailComponent,
    IssueFiltersComponent,
    IssueListComponent,
    LabelEditorComponent,
    NewIssueDialogComponent,
    SettingsComponent,
    TeamComponent,
  ],
  imports: [BrowserModule, BrowserAnimationsModule, AppRoutingModule, SharedModule],
  providers: [{ provide: MAT_FORM_FIELD_DEFAULT_OPTIONS, useValue: FORM_FIELD_DEFAULTS }],
  bootstrap: [AppComponent],
})
export class AppModule {}
