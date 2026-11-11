import { ComponentFixture, TestBed } from '@angular/core/testing';
import {
  MAT_LEGACY_DIALOG_DATA as MAT_DIALOG_DATA,
  MatLegacyDialogRef as MatDialogRef,
} from '@angular/material/legacy-dialog';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

import { MEMBERS } from '../../data/sample-data';
import { SharedModule } from '../../shared/shared.module';
import { NewIssueDialogComponent } from './new-issue-dialog.component';

describe('NewIssueDialogComponent', () => {
  let fixture: ComponentFixture<NewIssueDialogComponent>;
  let page: HTMLElement;
  let close: jasmine.Spy;

  beforeEach(async () => {
    close = jasmine.createSpy('close');
    await TestBed.configureTestingModule({
      imports: [NoopAnimationsModule, SharedModule],
      declarations: [NewIssueDialogComponent],
      providers: [
        { provide: MatDialogRef, useValue: { close } },
        { provide: MAT_DIALOG_DATA, useValue: { members: MEMBERS } },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(NewIssueDialogComponent);
    fixture.detectChanges();
    page = fixture.nativeElement;
  });

  function submit(): void {
    page.querySelector<HTMLButtonElement>('button[type="submit"]')?.click();
    fixture.detectChanges();
  }

  it('creates a medium-priority bug by default', () => {
    const title = page.querySelector<HTMLInputElement>('input[formControlName="title"]');
    if (title) {
      title.value = '  Tooltip hides the save button ';
      title.dispatchEvent(new Event('input'));
    }
    submit();
    expect(close).toHaveBeenCalledOnceWith({
      title: 'Tooltip hides the save button',
      type: 'bug',
      assignee: null,
      priority: 3,
    });
  });

  it('shows the priority it will use', () => {
    expect(page.querySelector('.priority-label')?.textContent).toContain('Priority: Medium');
    fixture.componentInstance.form.controls.priority.setValue(5);
    fixture.detectChanges();
    expect(page.querySelector('.priority-label')?.textContent).toContain('Priority: Highest');
  });

  it('requires a title', () => {
    submit();
    expect(close).not.toHaveBeenCalled();
    expect(page.textContent).toContain('A title is required');
  });
});
