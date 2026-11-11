import { TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { RouterTestingModule } from '@angular/router/testing';

import { AppComponent } from './app.component';
import { SharedModule } from './shared/shared.module';

describe('AppComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RouterTestingModule, NoopAnimationsModule, SharedModule],
      declarations: [AppComponent],
    }).compileComponents();
  });

  it('shows the app name in the toolbar', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const toolbar: HTMLElement = fixture.nativeElement.querySelector('.mat-toolbar');
    expect(toolbar.textContent).toContain('Triage');
  });

  it('links to every page', () => {
    const fixture = TestBed.createComponent(AppComponent);
    fixture.detectChanges();
    const links = Array.from<HTMLAnchorElement>(fixture.nativeElement.querySelectorAll('nav a'));
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/issues', '/board', '/team', '/settings']);
  });
});
