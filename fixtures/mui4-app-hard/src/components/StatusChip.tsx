import { Chip } from '@material-ui/core';
import { withStyles } from '@material-ui/core/styles';
import { Status } from '../data/issues';

const LABELS: Record<Status, string> = {
  open: 'Open',
  'in-progress': 'In progress',
  done: 'Done',
};

const SmallChip = withStyles({
  root: { height: 22, fontSize: 12 },
})(Chip);

export function StatusChip({ status, color }: { status: Status; color: string }) {
  return (
    <SmallChip
      label={LABELS[status]}
      variant="default"
      style={{ backgroundColor: color, color: '#fff' }}
    />
  );
}
