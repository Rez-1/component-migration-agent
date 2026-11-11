import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

import { SharedModule } from '../shared.module';
import { ConfirmButtonComponent } from './confirm-button.component';

describe('ConfirmButtonComponent', () => {
  let fixture: ComponentFixture<ConfirmButtonComponent>;
  let button: HTMLButtonElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NoopAnimationsModule, SharedModule],
    }).compileComponents();
    fixture = TestBed.createComponent(ConfirmButtonComponent);
    fixture.componentInstance.label = 'Close issue';
    fixture.componentInstance.confirmLabel = 'Close it for good?';
    fixture.detectChanges();
    button = fixture.nativeElement.querySelector('button');
  });

  function label(): string {
    return button.querySelector('.mat-button-wrapper')?.textContent?.trim() ?? '';
  }

  it('asks for confirmation on the first click', () => {
    expect(label()).toBe('Close issue');
    button.click();
    fixture.detectChanges();
    expect(label()).toBe('Close it for good?');
  });

  it('emits only on the second click', () => {
    let confirmed = 0;
    fixture.componentInstance.confirmed.subscribe(() => confirmed++);
    button.click();
    expect(confirmed).toBe(0);
    button.click();
    expect(confirmed).toBe(1);
  });

  it('disarms when focus leaves the button', () => {
    button.click();
    button.dispatchEvent(new Event('blur'));
    fixture.detectChanges();
    expect(fixture.componentInstance.armed).toBeFalse();
    expect(label()).toBe('Close issue');
  });
});
