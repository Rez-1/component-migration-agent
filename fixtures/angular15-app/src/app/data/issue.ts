export type IssueStatus = 'open' | 'in-progress' | 'closed';
export type IssueType = 'bug' | 'feature' | 'chore';

export interface IssueComment {
  author: string;
  text: string;
  posted: string;
}

export interface Issue {
  id: number;
  title: string;
  type: IssueType;
  status: IssueStatus;
  /** 1 (lowest) to 5 (highest). */
  priority: number;
  assignee: string | null;
  labels: string[];
  updated: string;
  description: string;
  comments: IssueComment[];
}

export interface Member {
  name: string;
  role: string;
  email: string;
}

export interface NewIssue {
  title: string;
  type: IssueType;
  assignee: string | null;
  priority: number;
}

export const STATUS_LABELS: Record<IssueStatus, string> = {
  open: 'Open',
  'in-progress': 'In progress',
  closed: 'Closed',
};
