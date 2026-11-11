import { Component, EventEmitter, Input, OnDestroy, OnInit, Output } from '@angular/core';
import { FormControl } from '@angular/forms';
import { Subscription } from 'rxjs';

/** A search field with a clear button. Emits the trimmed text on every change. */
@Component({
  selector: 'app-search-box',
  templateUrl: './search-box.component.html',
  styleUrls: ['./search-box.component.scss'],
})
export class SearchBoxComponent implements OnInit, OnDestroy {
  @Input() placeholder = 'Search';
  @Output() search = new EventEmitter<string>();

  readonly control = new FormControl('', { nonNullable: true });
  private subscription?: Subscription;

  ngOnInit(): void {
    this.subscription = this.control.valueChanges.subscribe((value) => this.search.emit(value.trim()));
  }

  ngOnDestroy(): void {
    this.subscription?.unsubscribe();
  }

  clear(): void {
    this.control.setValue('');
  }
}
