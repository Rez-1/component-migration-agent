import { ReactNode, useState } from 'react';
import { Button, CssBaseline, Toolbar } from '@material-ui/core';
import { ThemeProvider } from '@material-ui/core/styles';
import { theme } from './theme';
import { ISSUES } from './data/issues';
import { Board } from './screens/Board';
import { IssueList } from './screens/IssueList';
import { IssueDetail } from './screens/IssueDetail';
import { NewIssueDialog } from './screens/NewIssueDialog';
import { Activity } from './screens/Activity';
import { Reports } from './screens/Reports';

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {children}
    </ThemeProvider>
  );
}

const PAGES = ['Board', 'Issues', 'Activity', 'Reports'] as const;
type Page = typeof PAGES[number];

export function App() {
  const [page, setPage] = useState<Page>('Board');
  const [selected, setSelected] = useState<number | null>(null);
  const issue = ISSUES.find((i) => i.id === selected);
  return (
    <AppProviders>
      <Toolbar component="nav">
        {PAGES.map((p) => (
          <Button key={p} color={p === page ? 'primary' : 'inherit'} onClick={() => setPage(p)}>
            {p}
          </Button>
        ))}
        <NewIssueDialog onCreate={() => setPage('Issues')} />
      </Toolbar>
      {page === 'Board' && <Board issues={ISSUES} onOpen={setSelected} />}
      {page === 'Issues' && <IssueList issues={ISSUES} onOpen={setSelected} />}
      {page === 'Activity' && <Activity />}
      {page === 'Reports' && <Reports issues={ISSUES} />}
      {issue && <IssueDetail issue={issue} />}
    </AppProviders>
  );
}
