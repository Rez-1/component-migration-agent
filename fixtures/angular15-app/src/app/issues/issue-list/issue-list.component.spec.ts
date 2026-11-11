import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { Router } from '@angular/router';
import { RouterTestingModule } from '@angular/router/testing';

import { SharedModule } from '../../shared/shared.module';
import { IssueFiltersComponent } from '../issue-filters/issue-filters.component';
import { IssueListComponent } from './issue-list.component';

describe('IssueListComponent', () => {
  let fixture: ComponentFixture<IssueListComponent>;
  let page: HTMLElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NoopAnimationsModule, RouterTestingModule, SharedModule],
      declarations: [IssueListComponent, IssueFiltersComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(IssueListComponent);
    page = fixture.nativeElement;
    await settle();
  });

  /** The table updates its paginator asynchronously. */
  async function settle(): Promise<void> {
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  function rows(): HTMLElement[] {
    return Array.from(page.querySelectorAll('tr.issue-row'));
  }

  function summary(): string {
    return page.querySelector('.page-summary')?.textContent?.trim() ?? '';
  }

  async function nextPage(): Promise<void> {
    page.querySelector<HTMLButtonElement>('button[aria-label="Next page"]')?.click();
    await settle();
  }

  it('shows ten issues a page', () => {
    expect(rows().length).toBe(10);
    expect(summary()).toBe('Page 1 of 3');
  });

  it('pages through the issues', async () => {
    await nextPage();
    expect(rows()[0].textContent).toContain('111');
    expect(summary()).toBe('Page 2 of 3');
  });

  it('filters by the search text and goes back to the first page', async () => {
    await nextPage();
    const search = page.querySelector<HTMLInputElement>('app-search-box input');
    if (search) {
      search.value = 'page';
      search.dispatchEvent(new Event('input'));
    }
    await settle();
    expect(rows().map((row) => row.querySelector('.title-cell')?.textContent?.trim())).toEqual([
      'Login page loses the redirect after a timeout',
      'Assignee menu is cut off at the bottom of the page',
    ]);
    expect(summary()).toBe('Page 1 of 1');
  });

  it('opens an issue when its row is clicked', () => {
    const navigate = spyOn(TestBed.inject(Router), 'navigate');
    rows()[0].click();
    expect(navigate).toHaveBeenCalledWith(['/issues', 101]);
  });
});
