import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { RouterTestingModule } from '@angular/router/testing';

import { SharedModule } from '../shared/shared.module';
import { BoardComponent } from './board.component';

describe('BoardComponent', () => {
  let fixture: ComponentFixture<BoardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NoopAnimationsModule, RouterTestingModule, SharedModule],
      declarations: [BoardComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(BoardComponent);
    fixture.detectChanges();
  });

  function cards(status: string): HTMLElement[] {
    return Array.from(fixture.nativeElement.querySelectorAll(`[data-status="${status}"] mat-card`));
  }

  it('puts each issue in the column for its status', () => {
    expect(cards('open').length).toBe(11);
    expect(cards('in-progress').length).toBe(7);
    expect(cards('closed').length).toBe(4);
    expect(cards('closed')[0].textContent).toContain('#104 Board columns overflow on narrow screens');
  });

  it('shows the share of issues closed', () => {
    expect(fixture.nativeElement.querySelector('.done-figure').textContent.trim()).toBe('18%');
  });

  it('links each card to its issue', () => {
    const link = cards('open')[0].querySelector('a');
    expect(link?.getAttribute('href')).toBe('/issues/101');
  });
});
