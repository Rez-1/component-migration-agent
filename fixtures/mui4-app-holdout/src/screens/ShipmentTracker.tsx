import { Paper, Step, StepLabel, Stepper, Typography } from '@material-ui/core';

export const SHIPMENT_STEPS = ['Picked', 'Packed', 'Handed to carrier', 'Delivered'] as const;
export type ShipmentStage = typeof SHIPMENT_STEPS[number];

export interface Shipment {
  trackingNumber: string;
  carrier: string;
  stage: ShipmentStage;
}

export function ShipmentTracker({ shipment }: { shipment: Shipment }) {
  const active = SHIPMENT_STEPS.indexOf(shipment.stage);
  return (
    <Paper component="section" aria-labelledby="shipment-title" style={{ padding: 16 }}>
      <Typography id="shipment-title" variant="h6" component="h1">
        Shipment {shipment.trackingNumber}
      </Typography>
      <Typography variant="body2" color="textSecondary">
        {shipment.carrier}: {shipment.stage}
      </Typography>
      <Stepper activeStep={active} alternativeLabel>
        {SHIPMENT_STEPS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>
    </Paper>
  );
}
