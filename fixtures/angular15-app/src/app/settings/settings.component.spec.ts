import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatLegacySnackBar as MatSnackBar } from '@angular/material/legacy-snack-bar';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { Subject } from 'rxjs';

import { SharedModule } from '../shared/shared.module';
import { DEFAULT_PREFERENCES, SettingsComponent } from './settings.component';

describe('SettingsComponent', () => {
  let fixture: ComponentFixture<SettingsComponent>;
  let page: HTMLElement;
  let open: jasmine.Spy;
  let undo: Subject<void>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NoopAnimationsModule, SharedModule],
      declarations: [SettingsComponent],
    }).compileComponents();
    undo = new Subject<void>();
    open = spyOn(TestBed.inject(MatSnackBar), 'open').and.returnValue({
      onAction: () => undo.asObservable(),
    } as ReturnType<MatSnackBar['open']>);
    fixture = TestBed.createComponent(SettingsComponent);
    fixture.detectChanges();
    page = fixture.nativeElement;
  });

  function saveButton(): HTMLButtonElement {
    return page.querySelector('button[type="submit"]') as HTMLButtonElement;
  }

  function toggleEmail(): void {
    page.querySelector<HTMLInputElement>('mat-checkbox input')?.click();
    fixture.detectChanges();
  }

  it('saves only after a change', () => {
    expect(saveButton().disabled).toBeTrue();
    toggleEmail();
    expect(saveButton().disabled).toBeFalse();
    saveButton().click();
    fixture.detectChanges();
    expect(fixture.componentInstance.saved.emailOnNew).toBeFalse();
    expect(saveButton().disabled).toBeTrue();
  });

  it('confirms the save and can undo it', () => {
    toggleEmail();
    saveButton().click();
    expect(open).toHaveBeenCalledOnceWith('Settings saved', 'Undo', { duration: 5000 });
    undo.next();
    expect(fixture.componentInstance.saved).toEqual(DEFAULT_PREFERENCES);
    expect(fixture.componentInstance.form.getRawValue()).toEqual(DEFAULT_PREFERENCES);
  });

  it('rejects a capacity over twelve hours', () => {
    const capacity = page.querySelector<HTMLInputElement>('input[formControlName="dailyCapacity"]');
    if (capacity) {
      capacity.value = '14';
      capacity.dispatchEvent(new Event('input'));
      capacity.dispatchEvent(new Event('blur'));
    }
    fixture.detectChanges();
    expect(page.querySelector('.capacity')?.classList).toContain('mat-form-field-invalid');
    expect(page.textContent).toContain('Between 1 and 12 hours');
  });
});
