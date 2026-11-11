import { Component } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { Observable, switchMap } from 'rxjs';

import { Issue, STATUS_LABELS } from '../../data/issue';
import { IssueService } from '../../data/issue.service';

@Component({
  selector: 'app-issue-detail',
  templateUrl: './issue-detail.component.html',
  styleUrls: ['./issue-detail.component.scss'],
})
export class IssueDetailComponent {
  readonly statusLabels = STATUS_LABELS;
  readonly issue$: Observable<Issue | undefined> = this.route.paramMap.pipe(
    switchMap((params) => this.issues.issue$(Number(params.get('id')))),
  );

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    readonly issues: IssueService,
  ) {}

  setLabels(issue: Issue, labels: string[]): void {
    this.issues.update(issue.id, { labels });
  }

  close(issue: Issue): void {
    this.issues.setStatus(issue.id, 'closed');
  }

  back(): void {
    this.router.navigate(['/issues']);
  }
}
