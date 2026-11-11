import { ENTER } from '@angular/cdk/keycodes';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';

import { SharedModule } from '../../shared/shared.module';
import { LabelEditorComponent } from './label-editor.component';

describe('LabelEditorComponent', () => {
  let fixture: ComponentFixture<LabelEditorComponent>;
  let input: HTMLInputElement;
  let changes: string[][];

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [NoopAnimationsModule, SharedModule],
      declarations: [LabelEditorComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(LabelEditorComponent);
    fixture.componentInstance.labels = ['frontend'];
    changes = [];
    fixture.componentInstance.labelsChange.subscribe((labels: string[]) => changes.push(labels));
    fixture.detectChanges();
    input = fixture.nativeElement.querySelector('input');
  });

  function enter(text: string): void {
    input.value = text;
    input.dispatchEvent(new Event('input'));
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: ENTER } as KeyboardEventInit));
    fixture.detectChanges();
  }

  it('adds a label when Enter is pressed, in lower case', () => {
    enter('Needs Design');
    expect(changes).toEqual([['frontend', 'needs design']]);
    expect(input.value).toBe('');
  });

  it('ignores a label it already has', () => {
    enter('frontend');
    expect(changes).toEqual([]);
  });

  it('removes a label with its remove button', () => {
    fixture.nativeElement.querySelector('[aria-label="Remove frontend"]').click();
    expect(changes).toEqual([[]]);
  });
});
