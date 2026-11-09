export interface City {
  id: string;
  label: string;
  country: string;
}

export const CITIES: City[] = [
  { id: 'ams', label: 'Amsterdam', country: 'Netherlands' },
  { id: 'ber', label: 'Berlin', country: 'Germany' },
  { id: 'lis', label: 'Lisbon', country: 'Portugal' },
  { id: 'mad', label: 'Madrid', country: 'Spain' },
  { id: 'rot', label: 'Rotterdam', country: 'Netherlands' },
];
