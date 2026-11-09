import { screen } from '@testing-library/react';
import { renderScreen } from '../../test-utils';
import { ShipmentTracker } from '../ShipmentTracker';

describe('ShipmentTracker', () => {
  it('shows the carrier and the current stage', () => {
    renderScreen(
      <ShipmentTracker shipment={{ trackingNumber: 'TRK-1', carrier: 'DHL', stage: 'Handed to carrier' }} />,
    );

    expect(screen.getByRole('heading', { name: 'Shipment TRK-1' })).toBeInTheDocument();
    expect(screen.getByText('DHL: Handed to carrier')).toBeInTheDocument();
    expect(screen.getByText('Delivered')).toBeInTheDocument();
  });

  it('marks the finished stages as done', () => {
    const { container } = renderScreen(
      <ShipmentTracker shipment={{ trackingNumber: 'TRK-2', carrier: 'DHL', stage: 'Handed to carrier' }} />,
    );

    // Picked and Packed are done; the step icons carry no accessible state for it.
    expect(container.querySelectorAll('.MuiStepIcon-completed')).toHaveLength(2);
    expect(container.querySelectorAll('.MuiStepIcon-active')).toHaveLength(1);
  });
});
