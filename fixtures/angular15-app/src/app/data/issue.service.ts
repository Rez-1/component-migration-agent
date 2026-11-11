import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, map } from 'rxjs';

import { Issue, IssueStatus, Member, NewIssue } from './issue';
import { ISSUES, MEMBERS } from './sample-data';

/** Keeps the issues in memory. Every change is published through `issues$`. */
@Injectable({ providedIn: 'root' })
export class IssueService {
  private readonly issues = new BehaviorSubject<Issue[]>(ISSUES.map((issue) => ({ ...issue })));

  readonly issues$: Observable<Issue[]> = this.issues.asObservable();

  get members(): Member[] {
    return MEMBERS;
  }

  issue$(id: number): Observable<Issue | undefined> {
    return this.issues$.pipe(map((issues) => issues.find((issue) => issue.id === id)));
  }

  snapshot(): Issue[] {
    return this.issues.value;
  }

  create(draft: NewIssue): Issue {
    const issues = this.issues.value;
    const issue: Issue = {
      ...draft,
      id: Math.max(...issues.map((i) => i.id)) + 1,
      status: 'open',
      labels: [],
      updated: '2026-11-01',
      description: '',
      comments: [],
    };
    this.issues.next([issue, ...issues]);
    return issue;
  }

  update(id: number, changes: Partial<Issue>): void {
    this.issues.next(this.issues.value.map((i) => (i.id === id ? { ...i, ...changes } : i)));
  }

  setStatus(id: number, status: IssueStatus): void {
    this.update(id, { status });
  }

  openCount(member: string): number {
    return this.issues.value.filter((i) => i.assignee === member && i.status !== 'closed').length;
  }
}
