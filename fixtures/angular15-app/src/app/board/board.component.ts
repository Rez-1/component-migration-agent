import { Component } from '@angular/core';
import { Observable, map } from 'rxjs';

import { Issue, IssueStatus, STATUS_LABELS } from '../data/issue';
import { IssueService } from '../data/issue.service';

interface Column {
  status: IssueStatus;
  title: string;
  issues: Issue[];
}

@Component({
  selector: 'app-board',
  templateUrl: './board.component.html',
  styleUrls: ['./board.component.scss'],
})
export class BoardComponent {
  readonly columns$: Observable<Column[]> = this.issues.issues$.pipe(
    map((issues) =>
      (Object.keys(STATUS_LABELS) as IssueStatus[]).map((status) => ({
        status,
        title: STATUS_LABELS[status],
        issues: issues.filter((issue) => issue.status === status),
      })),
    ),
  );

  readonly done$: Observable<number> = this.issues.issues$.pipe(
    map((issues) => Math.round((100 * issues.filter((i) => i.status === 'closed').length) / issues.length)),
  );

  constructor(private readonly issues: IssueService) {}

  trackById(_index: number, issue: Issue): number {
    return issue.id;
  }
}
