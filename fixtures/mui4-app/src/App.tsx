import { ReactNode, useState } from 'react';
import { CssBaseline } from '@material-ui/core';
import { ThemeProvider } from '@material-ui/core/styles';
import { theme } from './theme';
import { Dashboard } from './screens/Dashboard';
import { UsersTable } from './screens/UsersTable';
import { Settings } from './screens/Settings';
import { AccountDialog } from './screens/AccountDialog';
import { ProfileCard } from './screens/ProfileCard';
import { Search } from './screens/Search';
import { Faq } from './screens/Faq';
import { Notifications } from './screens/Notifications';
import { ResponsiveNav } from './screens/ResponsiveNav';
import { ProfileForm } from './screens/ProfileForm';

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {children}
    </ThemeProvider>
  );
}

const PAGES = ['Dashboard', 'Users', 'Search', 'Account', 'Help'] as const;
type Page = typeof PAGES[number];

export function App() {
  const [page, setPage] = useState<Page>('Dashboard');
  return (
    <AppProviders>
      <ResponsiveNav pages={PAGES} current={page} onNavigate={(p) => setPage(p as Page)} />
      {page === 'Dashboard' && (
        <>
          <Notifications />
          <Dashboard />
        </>
      )}
      {page === 'Users' && <UsersTable />}
      {page === 'Search' && <Search />}
      {page === 'Account' && (
        <>
          <ProfileCard name="Ada Lovelace" role="Admin" email="ada@example.com" />
          <ProfileForm />
          <Settings />
          <AccountDialog />
        </>
      )}
      {page === 'Help' && <Faq />}
    </AppProviders>
  );
}
