import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

import { SharedModule } from '../shared.module';
import { SearchBoxComponent } from './search-box.component';

describe('SearchBoxComponent', () => {
  let fixture: ComponentFixture<SearchBoxComponent>;
  let input: HTMLInputElement;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NoopAnimationsModule, SharedModule],
    }).compileComponents();
    fixture = TestBed.createComponent(SearchBoxComponent);
    fixture.componentInstance.placeholder = 'Search issues';
    fixture.detectChanges();
    input = fixture.nativeElement.querySelector('input');
  });

  function type(text: string): void {
    input.value = text;
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
  }

  it('labels the field with its placeholder', () => {
    const label: HTMLLabelElement | null = fixture.nativeElement.querySelector('mat-form-field label');
    expect(label?.textContent?.trim()).toBe('Search issues');
    expect(label?.getAttribute('for')).toBe(input.id);
  });

  it('emits the trimmed text as the user types', () => {
    const searches: string[] = [];
    fixture.componentInstance.search.subscribe((text: string) => searches.push(text));
    type('  login ');
    expect(searches).toEqual(['login']);
  });

  it('offers a clear button once there is text', () => {
    expect(fixture.nativeElement.querySelector('[aria-label="Clear search"]')).toBeNull();
    type('board');
    fixture.nativeElement.querySelector('[aria-label="Clear search"]').click();
    fixture.detectChanges();
    expect(input.value).toBe('');
  });
});
