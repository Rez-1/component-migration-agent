export interface Person {
  id: string;
  name: string;
  initials: string;
}

export const TEAM: Person[] = [
  { id: 'ada', name: 'Ada Lovelace', initials: 'AL' },
  { id: 'grace', name: 'Grace Hopper', initials: 'GH' },
  { id: 'linus', name: 'Linus Torvalds', initials: 'LT' },
  { id: 'margaret', name: 'Margaret Hamilton', initials: 'MH' },
];

// The signed-in user, as the session endpoint returns it (a separate object from
// the team list, which comes from another endpoint).
export const CURRENT_USER: Person = { id: 'grace', name: 'Grace Hopper', initials: 'GH' };
