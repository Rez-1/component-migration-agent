import { Issue, Member } from './issue';

export const MEMBERS: Member[] = [
  { name: 'Ada Brandt', role: 'Backend', email: 'ada.brandt@example.com' },
  { name: 'Joris Kemp', role: 'Frontend', email: 'joris.kemp@example.com' },
  { name: 'Mina Osei', role: 'Design', email: 'mina.osei@example.com' },
  { name: 'Tomás Rey', role: 'Operations', email: 'tomas.rey@example.com' },
];

const TITLES: [string, Issue['type']][] = [
  ['Login page loses the redirect after a timeout', 'bug'],
  ['Export the issue table as CSV', 'feature'],
  ['Upgrade the build image to the new base', 'chore'],
  ['Board columns overflow on narrow screens', 'bug'],
  ['Bulk-assign issues from the table', 'feature'],
  ['Search ignores words with accents', 'bug'],
  ['Weekly digest email for watchers', 'feature'],
  ['Remove the unused reports endpoint', 'chore'],
  ['Labels with spaces break the filter URL', 'bug'],
  ['Keyboard shortcut to open a new issue', 'feature'],
  ['Pin the Node version in CI', 'chore'],
  ['Comment timestamps show the server time zone', 'bug'],
  ['Saved filters per user', 'feature'],
  ['Rotate the staging database credentials', 'chore'],
  ['Closing an issue twice logs an error', 'bug'],
  ['Dark mode for the board', 'feature'],
  ['Archive issues closed more than a year ago', 'chore'],
  ['Assignee menu is cut off at the bottom of the page', 'bug'],
  ['Show the estimate total per column', 'feature'],
  ['Move the logs to the shared bucket', 'chore'],
  ['Paste an image into a comment', 'feature'],
  ['Priority sort puts empty values first', 'bug'],
];

const STATUSES: Issue['status'][] = ['open', 'in-progress', 'open', 'closed', 'open', 'in-progress'];
const LABELS = [['frontend'], ['backend', 'api'], ['infra'], ['frontend', 'ux'], [], ['search']];

/** Fixed sample issues: the app has no backend of its own. */
export const ISSUES: Issue[] = TITLES.map(([title, type], i) => ({
  id: 101 + i,
  title,
  type,
  status: STATUSES[i % STATUSES.length],
  priority: (i % 5) + 1,
  assignee: i % 7 === 6 ? null : MEMBERS[i % MEMBERS.length].name,
  labels: [...LABELS[i % LABELS.length]],
  updated: `2026-10-${String(28 - i).padStart(2, '0')}`,
  description:
    'Steps to reproduce, expected behaviour and what happens instead are in the first comment.',
  comments: [
    { author: MEMBERS[(i + 1) % MEMBERS.length].name, text: 'I can reproduce this on the latest build.', posted: '2026-10-20' },
    { author: MEMBERS[(i + 2) % MEMBERS.length].name, text: 'Picking this up after the release.', posted: '2026-10-22' },
  ],
}));
