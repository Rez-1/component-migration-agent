import { ChangeEvent } from 'react';
import { Slider, Typography } from '@material-ui/core';

export interface RangeSliderProps {
  id: string;
  label: string;
  min: number;
  max: number;
  value: [number, number];
  onChange: (event: ChangeEvent<unknown>, value: number | number[]) => void;
  unit?: string;
}

export function RangeSlider({ id, label, min, max, value, onChange, unit = '' }: RangeSliderProps) {
  return (
    <div>
      <Typography id={id} gutterBottom>
        {label}: {value[0]}–{value[1]}
        {unit}
      </Typography>
      <Slider
        aria-labelledby={id}
        getAriaValueText={(v) => `${v}${unit}`}
        min={min}
        max={max}
        value={value}
        onChange={onChange}
        valueLabelDisplay="auto"
      />
    </div>
  );
}
