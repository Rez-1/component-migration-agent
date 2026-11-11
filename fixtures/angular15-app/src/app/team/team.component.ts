import { Component } from '@angular/core';
import { MatLegacySnackBar as MatSnackBar } from '@angular/material/legacy-snack-bar';

import { Member } from '../data/issue';
import { IssueService } from '../data/issue.service';

@Component({
  selector: 'app-team',
  templateUrl: './team.component.html',
  styleUrls: ['./team.component.scss'],
})
export class TeamComponent {
  constructor(readonly issues: IssueService, private readonly snackBar: MatSnackBar) {}

  initials(member: Member): string {
    return member.name
      .split(' ')
      .map((part) => part[0])
      .join('');
  }

  copyEmail(member: Member): void {
    navigator.clipboard?.writeText(member.email);
    this.snackBar.open(`Copied ${member.email}`, undefined, { duration: 2500 });
  }
}
