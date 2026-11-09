import { Avatar, Card, CardContent, Typography } from '@material-ui/core';
import { makeStyles, Theme } from '@material-ui/core/styles';

const useStyles = makeStyles((theme: Theme) => ({
  root: {
    display: 'flex',
    alignItems: 'center',
    gap: theme.spacing(2),
    padding: theme.spacing(2),
  },
  avatar: {
    width: theme.spacing(7),
    height: theme.spacing(7),
    backgroundColor: theme.palette.primary.main,
  },
}));

export interface ProfileCardProps {
  name: string;
  role: string;
  email: string;
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .slice(0, 2)
    .join('');
}

export function ProfileCard({ name, role, email }: ProfileCardProps) {
  const classes = useStyles();
  return (
    <Card component="article" aria-label={`Profile of ${name}`}>
      <CardContent className={classes.root}>
        <Avatar className={classes.avatar} aria-hidden>
          {initials(name)}
        </Avatar>
        <div>
          <Typography variant="h6" component="h2">
            {name}
          </Typography>
          <Typography color="textSecondary">{role}</Typography>
          <Typography variant="body2">{email}</Typography>
        </div>
      </CardContent>
    </Card>
  );
}
