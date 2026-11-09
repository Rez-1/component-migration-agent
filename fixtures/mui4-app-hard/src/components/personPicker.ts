import { Person } from '../data/people';

// Shared by every Autocomplete that picks a team member.
export const personPickerProps = {
  getOptionLabel: (person: Person) => person.name,
  getOptionSelected: (option: Person, value: Person) => option.id === value.id,
  autoHighlight: true,
};
