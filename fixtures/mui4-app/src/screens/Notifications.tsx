import { useState } from 'react';
import {
  Badge,
  Button,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Paper,
  Typography,
} from '@material-ui/core';
import NotificationsIcon from '@material-ui/icons/Notifications';
import MailIcon from '@material-ui/icons/Mail';

export interface Notice {
  id: number;
  text: string;
  read: boolean;
}

const NOTICES: Notice[] = [
  { id: 1, text: 'Alan Turing joined your workspace', read: false },
  { id: 2, text: 'Your export is ready', read: false },
  { id: 3, text: 'Weekly digest sent', read: true },
  { id: 4, text: 'Grace Hopper changed her role', read: false },
];

export function Notifications({ initial = NOTICES }: { initial?: Notice[] }) {
  const [notices, setNotices] = useState(initial);
  const unread = notices.filter((n) => !n.read).length;

  return (
    <Paper component="section" aria-labelledby="notifications-title">
      <Typography id="notifications-title" variant="h6" component="h1">
        <Badge badgeContent={unread} color="secondary">
          <NotificationsIcon aria-hidden />
        </Badge>{' '}
        Notifications
        <Typography variant="srOnly" component="span">
          {unread === 0 ? 'No unread notifications' : `${unread} unread notifications`}
        </Typography>
      </Typography>
      <List dense>
        {notices.map((n) => (
          <ListItem key={n.id} selected={!n.read}>
            <ListItemIcon>
              <MailIcon color={n.read ? 'disabled' : 'primary'} />
            </ListItemIcon>
            <ListItemText primary={n.text} secondary={n.read ? 'Read' : 'Unread'} />
          </ListItem>
        ))}
      </List>
      <Button
        disabled={unread === 0}
        onClick={() => setNotices(notices.map((n) => ({ ...n, read: true })))}
      >
        Mark all as read
      </Button>
    </Paper>
  );
}
