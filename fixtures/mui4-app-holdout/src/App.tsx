import { ReactNode, useState } from 'react';
import { AppBar, CssBaseline, Tab, Tabs, Toolbar, Typography } from '@material-ui/core';
import { ThemeProvider } from '@material-ui/core/styles';
import { theme } from './theme';
import { Order } from './data/orders';
import { StockSummary } from './screens/StockSummary';
import { OrdersTable } from './screens/OrdersTable';
import { OrderDialog } from './screens/OrderDialog';
import { Inventory } from './screens/Inventory';
import { ProductTags } from './screens/ProductTags';
import { ReturnForm } from './screens/ReturnForm';
import { ShipmentTracker } from './screens/ShipmentTracker';

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {children}
    </ThemeProvider>
  );
}

const SECTIONS = ['Overview', 'Orders', 'Stock', 'Returns'] as const;
type Section = typeof SECTIONS[number];

export function App() {
  const [section, setSection] = useState<Section>('Overview');
  const [openOrder, setOpenOrder] = useState<Order | null>(null);
  return (
    <AppProviders>
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" component="span">
            Back office
          </Typography>
        </Toolbar>
        <Tabs value={section} onChange={(_event, value) => setSection(value)}>
          {SECTIONS.map((s) => (
            <Tab key={s} value={s} label={s} />
          ))}
        </Tabs>
      </AppBar>
      {section === 'Overview' && (
        <>
          <StockSummary />
          <ShipmentTracker shipment={{ trackingNumber: 'TRK-88412', carrier: 'PostNL', stage: 'Packed' }} />
        </>
      )}
      {section === 'Orders' && (
        <>
          <OrdersTable onOpen={setOpenOrder} />
          {openOrder && <OrderDialog order={openOrder} open onClose={() => setOpenOrder(null)} />}
        </>
      )}
      {section === 'Stock' && (
        <>
          <Inventory />
          <ProductTags sku="MUG-001" initial={['fragile']} />
        </>
      )}
      {section === 'Returns' && <ReturnForm />}
    </AppProviders>
  );
}
