import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { RouterTestingModule } from '@angular/router/testing';
import { of } from 'rxjs';

import { IssueService } from '../../data/issue.service';
import { SharedModule } from '../../shared/shared.module';
import { LabelEditorComponent } from '../label-editor/label-editor.component';
import { IssueDetailComponent } from './issue-detail.component';

describe('IssueDetailComponent', () => {
  let fixture: ComponentFixture<IssueDetailComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NoopAnimationsModule, RouterTestingModule, SharedModule],
      declarations: [IssueDetailComponent, LabelEditorComponent],
      providers: [{ provide: ActivatedRoute, useValue: { paramMap: of(convertToParamMap({ id: '102' })) } }],
    }).compileComponents();
    fixture = TestBed.createComponent(IssueDetailComponent);
    fixture.detectChanges();
  });

  it('shows the issue with its labels and comments', () => {
    const page: HTMLElement = fixture.nativeElement;
    expect(page.querySelector('mat-card-title')?.textContent).toContain('#102 Export the issue table as CSV');
    expect(page.querySelector('.current-labels')?.textContent).toContain('backend');
    expect(page.querySelectorAll('.comment').length).toBe(2);
  });

  it('closes the issue after the second click', () => {
    const button: HTMLButtonElement = fixture.nativeElement.querySelector('app-confirm-button button');
    button.click();
    fixture.detectChanges();
    expect(TestBed.inject(IssueService).snapshot().find((i) => i.id === 102)?.status).toBe('in-progress');
    button.click();
    fixture.detectChanges();
    expect(TestBed.inject(IssueService).snapshot().find((i) => i.id === 102)?.status).toBe('closed');
    expect(fixture.nativeElement.querySelector('app-confirm-button')).toBeNull();
  });
});
