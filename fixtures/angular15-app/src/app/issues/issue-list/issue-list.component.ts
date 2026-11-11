import { AfterViewInit, Component, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { MatLegacyDialog as MatDialog } from '@angular/material/legacy-dialog';
import {
  MAT_LEGACY_PAGINATOR_DEFAULT_OPTIONS as MAT_PAGINATOR_DEFAULT_OPTIONS,
  MatLegacyPaginator as MatPaginator,
  MatLegacyPaginatorDefaultOptions as MatPaginatorDefaultOptions,
} from '@angular/material/legacy-paginator';
import { MatSort } from '@angular/material/sort';
import { MatLegacyTableDataSource as MatTableDataSource } from '@angular/material/legacy-table';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';

import { Issue, STATUS_LABELS } from '../../data/issue';
import { IssueService } from '../../data/issue.service';
import { IssueFilters } from '../issue-filters/issue-filters.component';
import { NewIssueDialogComponent } from '../new-issue-dialog/new-issue-dialog.component';

/** The page-size picker matches the filters above the table. */
const PAGINATOR_DEFAULTS: MatPaginatorDefaultOptions = {
  pageSize: 10,
  pageSizeOptions: [10, 25, 50],
  formFieldAppearance: 'standard',
};

@Component({
  selector: 'app-issue-list',
  templateUrl: './issue-list.component.html',
  styleUrls: ['./issue-list.component.scss'],
  providers: [{ provide: MAT_PAGINATOR_DEFAULT_OPTIONS, useValue: PAGINATOR_DEFAULTS }],
})
export class IssueListComponent implements OnInit, AfterViewInit, OnDestroy {
  readonly columns = ['id', 'title', 'status', 'priority', 'assignee', 'updated'];
  readonly dataSource = new MatTableDataSource<Issue>([]);

  filters: IssueFilters = { status: 'all', assignee: null };
  private text = '';
  private subscription?: Subscription;

  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;

  constructor(
    readonly issues: IssueService,
    private readonly dialog: MatDialog,
    private readonly router: Router,
  ) {
    this.dataSource.filterPredicate = (issue) => this.matches(issue);
  }

  ngOnInit(): void {
    this.subscription = this.issues.issues$.subscribe((issues) => (this.dataSource.data = issues));
  }

  ngAfterViewInit(): void {
    this.dataSource.paginator = this.paginator;
    this.dataSource.sort = this.sort;
  }

  ngOnDestroy(): void {
    this.subscription?.unsubscribe();
  }

  /** "Page 2 of 3", under the table. */
  get pageSummary(): string {
    const paginator = this.dataSource.paginator;
    if (!paginator || paginator.length === 0) {
      return 'No issues';
    }
    return `Page ${paginator.pageIndex + 1} of ${paginator.getNumberOfPages()}`;
  }

  statusLabel(issue: Issue): string {
    return STATUS_LABELS[issue.status];
  }

  onSearch(text: string): void {
    this.text = text.toLowerCase();
    this.applyFilter();
  }

  onFilters(filters: IssueFilters): void {
    this.filters = filters;
    this.applyFilter();
  }

  open(issue: Issue): void {
    this.router.navigate(['/issues', issue.id]);
  }

  newIssue(): void {
    this.dialog
      .open(NewIssueDialogComponent, { width: '480px', data: { members: this.issues.members } })
      .afterClosed()
      .subscribe((draft) => draft && this.issues.create(draft));
  }

  private applyFilter(): void {
    // Any non-empty string makes MatTableDataSource run the predicate.
    this.dataSource.filter = JSON.stringify([this.text, this.filters]);
    this.dataSource.paginator?.firstPage();
  }

  private matches(issue: Issue): boolean {
    const { status, assignee } = this.filters;
    return (
      (status === 'all' || issue.status === status) &&
      (assignee === null || issue.assignee === assignee) &&
      (this.text === '' || issue.title.toLowerCase().includes(this.text))
    );
  }
}
