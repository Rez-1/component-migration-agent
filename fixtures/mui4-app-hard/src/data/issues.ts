export type Status = 'open' | 'in-progress' | 'done';
export type Priority = 'low' | 'medium' | 'high';

export interface Label {
  id: string;
  name: string;
}

export interface Issue {
  id: number;
  title: string;
  status: Status;
  priority: Priority;
  assignee: string | null;
  labels: Label[];
  daysOpen: number;
}

export const LABELS: Label[] = [
  { id: 'bug', name: 'bug' },
  { id: 'design', name: 'design' },
  { id: 'docs', name: 'docs' },
  { id: 'perf', name: 'performance' },
  { id: 'security', name: 'security' },
];

const titles = [
  'Login form loses focus on error',
  'Export to CSV skips archived issues',
  'Dark mode contrast on badges',
  'Search ignores accents',
  'Rate-limit the public API',
  'Board columns jump on drag',
  'Document the webhook payload',
  'Slow query on the activity feed',
  'Avatar upload rejects PNG files',
  'Keyboard shortcut for new issue',
  'Timezone shown in due dates',
  'Email digest sent twice',
];

const statuses: Status[] = ['open', 'in-progress', 'done'];
const priorities: Priority[] = ['high', 'medium', 'low'];
const people = ['ada', 'grace', 'linus', null];

export const ISSUES: Issue[] = titles.map((title, i) => ({
  id: 101 + i,
  title,
  status: statuses[i % 3],
  priority: priorities[i % 3],
  assignee: people[i % 4],
  labels: i % 2 === 0 ? [LABELS[0]] : [LABELS[2]],
  daysOpen: (i * 7) % 30,
}));
