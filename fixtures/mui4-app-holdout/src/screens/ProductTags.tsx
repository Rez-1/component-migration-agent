import { useState } from 'react';
import { TextField, Typography } from '@material-ui/core';
import { Autocomplete } from '@material-ui/lab';
import { KNOWN_TAGS } from '../data/products';

// New tags typed by staff are stored lower-case and hyphenated, like the known ones.
const normaliseTag = (raw: string) => raw.trim().toLowerCase().replace(/\s+/g, '-');

export function ProductTags({
  sku,
  initial = [],
  onChange,
}: {
  sku: string;
  initial?: string[];
  onChange?: (tags: string[]) => void;
}) {
  const [tags, setTags] = useState<string[]>(initial);
  const [lastRemoved, setLastRemoved] = useState<string | null>(null);

  return (
    <section aria-labelledby="tags-title">
      <Typography id="tags-title" variant="h6" component="h1">
        Tags for {sku}
      </Typography>
      <Autocomplete
        multiple
        freeSolo
        options={KNOWN_TAGS}
        value={tags}
        onChange={(_event, value, reason) => {
          let next = value;
          if (reason === 'create-option') {
            next = Array.from(new Set(value.map(normaliseTag)));
          }
          if (reason === 'remove-option') {
            setLastRemoved(tags.find((t) => !value.includes(t)) ?? null);
          }
          setTags(next);
          onChange?.(next);
        }}
        renderInput={(params) => <TextField {...params} label="Tags" placeholder="Add a tag" />}
      />
      {lastRemoved && (
        <Typography role="status" variant="body2">
          Removed {lastRemoved}
        </Typography>
      )}
    </section>
  );
}
