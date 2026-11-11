import { OverlayContainer } from '@angular/cdk/overlay';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatLegacySelect as MatSelect } from '@angular/material/legacy-select';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { By } from '@angular/platform-browser';

import { MEMBERS } from '../../data/sample-data';
import { SharedModule } from '../../shared/shared.module';
import { IssueFilters, IssueFiltersComponent } from './issue-filters.component';

describe('IssueFiltersComponent', () => {
  let fixture: ComponentFixture<IssueFiltersComponent>;
  let overlay: HTMLElement;
  let emitted: IssueFilters[];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NoopAnimationsModule, SharedModule],
      declarations: [IssueFiltersComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(IssueFiltersComponent);
    fixture.componentInstance.members = MEMBERS;
    emitted = [];
    fixture.componentInstance.filtersChange.subscribe((f: IssueFilters) => emitted.push(f));
    fixture.detectChanges();
    overlay = TestBed.inject(OverlayContainer).getContainerElement();
  });

  function open(index: number): HTMLElement[] {
    const select: MatSelect = fixture.debugElement.queryAll(By.directive(MatSelect))[index].componentInstance;
    select.open();
    fixture.detectChanges();
    return Array.from(overlay.querySelectorAll('mat-option'));
  }

  it('emits the chosen status', () => {
    const options = open(0);
    options.find((o) => o.textContent?.trim() === 'In progress')?.click();
    expect(emitted).toEqual([{ status: 'in-progress', assignee: null }]);
  });

  it('offers every member as an assignee, and anyone', () => {
    const options = open(1);
    expect(options.map((o) => o.textContent?.trim())).toEqual(['Anyone', ...MEMBERS.map((m) => m.name)]);
    options[3].click();
    expect(emitted).toEqual([{ status: 'all', assignee: 'Mina Osei' }]);
  });
});
