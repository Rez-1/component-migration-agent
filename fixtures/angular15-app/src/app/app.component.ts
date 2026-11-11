import { Component } from '@angular/core';
import { MatLegacyDialog as MatDialog } from '@angular/material/legacy-dialog';

import { IssueService } from './data/issue.service';
import { NewIssueDialogComponent } from './issues/new-issue-dialog/new-issue-dialog.component';

@Component({
  selector: 'app-root',
  template: `
    <mat-toolbar color="primary" class="app-toolbar">
      <span class="brand">Triage</span>
      <nav class="nav">
        <a mat-button routerLink="/issues" routerLinkActive="active">Issues</a>
        <a mat-button routerLink="/board" routerLinkActive="active">Board</a>
        <a mat-button routerLink="/team" routerLinkActive="active">Team</a>
        <a mat-button routerLink="/settings" routerLinkActive="active">Settings</a>
      </nav>
      <span class="spacer"></span>
      <button mat-stroked-button color="accent" type="button" class="quick-add" (click)="quickAdd()">
        <mat-icon>bolt</mat-icon>
        Quick add
      </button>
    </mat-toolbar>
    <main>
      <router-outlet></router-outlet>
    </main>
  `,
  styles: [
    `
      .brand {
        font-weight: 500;
        margin-right: 24px;
      }
      .spacer {
        flex: 1;
      }
      .nav .active {
        background: rgba(255, 255, 255, 0.15);
      }
      .quick-add {
        color: #fff;
      }
    `,
  ],
})
export class AppComponent {
  constructor(private readonly dialog: MatDialog, private readonly issues: IssueService) {}

  quickAdd(): void {
    this.dialog
      .open(NewIssueDialogComponent, { width: '480px', data: { members: this.issues.members } })
      .afterClosed()
      .subscribe((draft) => draft && this.issues.create(draft));
  }
}
