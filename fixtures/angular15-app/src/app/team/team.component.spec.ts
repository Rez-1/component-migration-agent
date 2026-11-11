import { OverlayContainer } from '@angular/cdk/overlay';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

import { SharedModule } from '../shared/shared.module';
import { TeamComponent } from './team.component';

describe('TeamComponent', () => {
  let fixture: ComponentFixture<TeamComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NoopAnimationsModule, SharedModule],
      declarations: [TeamComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(TeamComponent);
    fixture.detectChanges();
  });

  it('lists every member with their open issues', () => {
    const rows = Array.from<HTMLElement>(fixture.nativeElement.querySelectorAll('.member'));
    expect(rows.length).toBe(4);
    expect(rows[0].querySelector('.name')?.textContent).toBe('Ada Brandt');
    expect(rows[0].querySelector('.open-count')?.textContent?.trim()).toBe('5 open');
    expect(rows[0].querySelector('.avatar')?.textContent).toBe('AB');
  });

  it("offers to copy a member's email", () => {
    fixture.nativeElement.querySelector('[aria-label="Actions for Mina Osei"]').click();
    fixture.detectChanges();
    const items = Array.from<HTMLElement>(
      TestBed.inject(OverlayContainer).getContainerElement().querySelectorAll('[mat-menu-item]'),
    );
    expect(items.length).toBe(1);
    expect(items[0].textContent).toContain('Copy email');
  });
});
