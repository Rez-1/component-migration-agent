import { Component, EventEmitter, Input, Output } from '@angular/core';

import { IssueStatus, Member, STATUS_LABELS } from '../../data/issue';

export interface IssueFilters {
  status: IssueStatus | 'all';
  assignee: string | null;
}

/** The status and assignee pickers above the issue table. */
@Component({
  selector: 'app-issue-filters',
  templateUrl: './issue-filters.component.html',
  styleUrls: ['./issue-filters.component.scss'],
})
export class IssueFiltersComponent {
  @Input() members: Member[] = [];
  @Input() filters: IssueFilters = { status: 'all', assignee: null };
  @Output() filtersChange = new EventEmitter<IssueFilters>();

  readonly statuses = Object.entries(STATUS_LABELS) as [IssueStatus, string][];

  setStatus(status: IssueStatus | 'all'): void {
    this.filters = { ...this.filters, status };
    this.filtersChange.emit(this.filters);
  }

  setAssignee(assignee: string | null): void {
    this.filters = { ...this.filters, assignee };
    this.filtersChange.emit(this.filters);
  }
}
