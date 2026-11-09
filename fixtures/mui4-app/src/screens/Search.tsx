import { useState } from 'react';
import { Autocomplete } from '@material-ui/lab';
import { TextField, Typography } from '@material-ui/core';
import { makeStyles, Theme } from '@material-ui/core/styles';
import { CITIES, City } from '../data/cities';

const useStyles = makeStyles((theme: Theme) => ({
  root: {
    padding: theme.spacing(2),
    maxWidth: 420,
  },
  option: {
    display: 'flex',
    justifyContent: 'space-between',
    width: '100%',
  },
  country: {
    color: theme.palette.text.secondary,
  },
}));

export function Search({ onSelect }: { onSelect?: (city: City | null) => void }) {
  const classes = useStyles();
  const [city, setCity] = useState<City | null>(null);

  return (
    <section className={classes.root} aria-labelledby="search-title">
      <Typography id="search-title" variant="h6" component="h1">
        Find an office
      </Typography>
      <Autocomplete
        options={CITIES}
        value={city}
        onChange={(_, value) => {
          setCity(value);
          onSelect?.(value);
        }}
        getOptionSelected={(a, b) => a.id === b.id}
        renderOption={(option) => (
          <span className={classes.option}>
            {option.label}
            <span className={classes.country}>{option.country}</span>
          </span>
        )}
        getOptionLabel={(option) => option.label}
        renderInput={(params) => <TextField {...params} label="City" variant="outlined" />}
      />
      {city && (
        <Typography role="status">
          Selected office: {city.label}, {city.country}
        </Typography>
      )}
    </section>
  );
}
